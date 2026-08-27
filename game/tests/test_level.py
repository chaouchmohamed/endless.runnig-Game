"""Tests for the level pacing curves and the generator's solvability guarantee.

The important one is ``test_every_row_is_solvable``: it walks all 200 levels and
asserts that no row can trap the player. If a future balance change breaks that,
this is what catches it.
"""

from __future__ import annotations

import pytest

import level as level_mod
import obstacles
from settings import (
    DISTANCE_ANCHORS,
    LANE_SWITCH_TIME,
    MAX_LEVEL,
    PLAYER_H,
    SLIDE_H_FACTOR,
    SPEED_BASE,
    SPEED_MAX,
)

ALL_LEVELS = range(1, MAX_LEVEL + 1)


# --------------------------------------------------------------------------
# Distance curve
# --------------------------------------------------------------------------


def test_distance_hits_every_anchor_exactly():
    for lvl, metres in DISTANCE_ANCHORS:
        assert level_mod.distance_for(lvl) == pytest.approx(float(metres))


def test_distance_is_monotonic():
    prev = 0.0
    for lvl in ALL_LEVELS:
        d = level_mod.distance_for(lvl)
        assert d >= prev, f"level {lvl} is shorter than level {lvl - 1}"
        prev = d


def test_distance_clamps_outside_range():
    assert level_mod.distance_for(0) == level_mod.distance_for(1)
    assert level_mod.distance_for(9999) == level_mod.distance_for(MAX_LEVEL)


# --------------------------------------------------------------------------
# Speed curve
# --------------------------------------------------------------------------


def test_speed_spans_the_configured_range():
    assert level_mod.speed_for(1) == pytest.approx(SPEED_BASE)
    assert level_mod.speed_for(MAX_LEVEL) == pytest.approx(SPEED_MAX)


def test_speed_is_monotonic_and_start_leaves_headroom():
    prev = 0.0
    for lvl in ALL_LEVELS:
        cap = level_mod.speed_for(lvl)
        assert cap >= prev
        prev = cap
        start = level_mod.start_speed_for(lvl)
        assert SPEED_BASE - 1e-6 <= start <= cap + 1e-6


# --------------------------------------------------------------------------
# Bands
# --------------------------------------------------------------------------


def test_bands_unlock_and_never_relock():
    seen = {k: False for k in level_mod.bands_for(1)}
    for lvl in ALL_LEVELS:
        bands = level_mod.bands_for(lvl)
        for key, value in bands.items():
            if seen[key]:
                assert value, f"band {key} re-locked at level {lvl}"
            seen[key] = seen[key] or value
    assert all(seen.values()), "some bands never unlock"


def test_early_levels_have_no_advanced_hazards():
    passable, impassable = level_mod.kind_pool(1)
    assert "mover" not in impassable
    assert "train" not in impassable
    assert "crusher" not in impassable


# --------------------------------------------------------------------------
# Solvability
# --------------------------------------------------------------------------


def _passable_lanes(row):
    """Lanes a player could get through, and what each demands.

    Returns ``{lane: action}``. A lane covered by an impassable obstacle is
    absent. Anything overlapping is resolved worst-case: if two obstacles cover
    one lane and either blocks, that lane is out.
    """
    lanes = {0: "clear", 1: "clear", 2: "clear"}
    for lane, kind in row:
        spec = obstacles.KINDS[kind]
        covered = (lane,) if spec["lanes"] == 1 else (
            tuple(sorted((lane, lane + 1 if lane < 2 else lane - 1))))
        for l in covered:
            if l not in lanes:
                continue
            if spec["action"] in ("jump", "slide"):
                # Two actions demanded in one lane is impossible to satisfy.
                if lanes[l] not in ("clear", spec["action"]):
                    del lanes[l]
                else:
                    lanes[l] = spec["action"]
            else:
                lanes.pop(l, None)
    return lanes


@pytest.mark.parametrize("lvl", list(ALL_LEVELS))
def test_every_row_is_solvable(lvl):
    """No row may leave the player with nowhere to go."""
    plan = level_mod.get_plan(lvl)
    assert plan.rows, f"level {lvl} generated no rows"

    reachable = {1}
    prev_z = 0.0
    for z, row in plan.rows:
        # How many lane changes fit in the gap since the previous row.
        gap_time = (z - prev_z) / plan.cap_speed
        hops = max(1, int(gap_time / LANE_SWITCH_TIME))

        options = _passable_lanes(row)
        assert options, f"level {lvl} row at z={z:.0f} blocks all three lanes"

        landing = {l for l in options
                   if any(abs(l - src) <= hops for src in reachable)}
        assert landing, (f"level {lvl} row at z={z:.0f}: passable lanes "
                         f"{sorted(options)} unreachable from {sorted(reachable)} "
                         f"in {hops} hop(s)")
        reachable = landing
        prev_z = z


def test_geometry_actually_admits_the_intended_action():
    """The boxes must match the actions the generator trusts them to have."""
    standing = PLAYER_H
    sliding = PLAYER_H * SLIDE_H_FACTOR

    for kind, spec in obstacles.KINDS.items():
        y0, y1 = spec["y"], spec["y"] + spec["h"]
        if spec["action"] == "slide":
            # A sliding player fits under it; a standing one does not.
            assert y0 >= sliding, f"{kind} is too low to slide under"
            assert y0 < standing, f"{kind} can be run through standing up"
        elif spec["action"] == "jump" and kind != "pit":
            # Jump peak is ~97 units (JUMP_V^2 / 2*GRAVITY).
            assert y1 < 97.0, f"{kind} is too tall to jump ({y1})"


def test_plans_are_deterministic():
    a = level_mod.LevelPlan(73)
    b = level_mod.LevelPlan(73)
    assert a.rows == b.rows
    assert a.coins == b.coins
    assert a.powerups == b.powerups
    assert a.par_score == b.par_score


def test_get_plan_caches_and_stays_bounded():
    for lvl in ALL_LEVELS:
        level_mod.get_plan(lvl)
    assert len(level_mod._PLANS) <= 25


# --------------------------------------------------------------------------
# Content and scoring
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lvl", [1, 25, 50, 100, 150, 200])
def test_levels_have_content(lvl):
    plan = level_mod.get_plan(lvl)
    assert len(plan.rows) >= 5
    assert len(plan.coins) >= 10
    assert plan.par_score > 0
    assert 0 < plan.star2 < plan.star3 < plan.par_score


def test_star_thresholds_are_ordered():
    for lvl in (1, 40, 111, 200):
        plan = level_mod.get_plan(lvl)
        assert plan.stars_for(0) == 1
        assert plan.stars_for(plan.star2) == 2
        assert plan.stars_for(plan.star3) == 3
        assert plan.stars_for(plan.par_score * 10) == 3


def test_final_level_is_special():
    plan = level_mod.get_plan(200)
    assert plan.is_final
    assert plan.name == "THE FINAL ADVENTURE"
    assert plan.reward == 250_000


def test_rewards_increase_with_level():
    prev = 0
    for lvl in range(1, MAX_LEVEL):
        r = level_mod.reward_for(lvl)
        assert r > prev
        prev = r
    assert level_mod.reward_for(MAX_LEVEL) > prev
