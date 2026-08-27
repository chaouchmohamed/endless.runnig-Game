"""
level.py - The 200 levels: pacing curve, difficulty bands, and generation.

Two guarantees hold for every level:

**Deterministic.** A level is seeded from its own number, so attempt 40 of
level 137 is byte-identical to attempt 1. Players can learn a level, and tests
can assert things about all 200 of them.

**Solvable.** The generator never emits a row the player cannot get through. It
tracks one notional safe lane and only ever moves it somewhere genuinely
reachable, given ``LANE_SWITCH_TIME`` and the level's top speed. Gaps are sized
in world units against the *cap* speed, so the real time the player gets is
always at least what was planned. ``tests/test_level.py`` re-verifies this
across all 200 levels.
"""

from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple

import obstacles
import world
from settings import (
    BAND_ADVANCED,
    BAND_COMBO,
    BAND_EXTREME,
    BAND_FAST,
    BAND_JUMPY,
    BAND_MOVING,
    BAND_VERYFAST,
    DISTANCE_ANCHORS,
    FINAL_LEVEL,
    FINAL_LEVEL_NAME,
    FINAL_LEVEL_REWARD,
    LANE_SWITCH_TIME,
    MAX_LEVEL,
    METER,
    PLAYER_D,
    POWERUP_BASE_TIME,
    SCORE_PER_COIN,
    SCORE_PER_DODGE,
    SCORE_PER_METER,
    SCORE_PER_POWERUP,
    SPEED_BASE,
    SPEED_MAX,
)

# Layout margins, in world units.
FIRST_ROW = 1500.0            # clear run-up before the first hazard
END_CLEAR = 900.0             # clear approach to the finish gate
COIN_SPACING = 78.0           # gap between coins inside one group
POWERUP_SPACING = 1500.0      # world units between power-up pickups


# --------------------------------------------------------------------------
# Pacing curves
# --------------------------------------------------------------------------


def clamp_level(level: int) -> int:
    return max(1, min(MAX_LEVEL, int(level)))


def distance_for(level: int) -> float:
    """Target distance in metres, interpolated through DISTANCE_ANCHORS.

    The anchors are hit exactly; everything between them is linear, so the curve
    is smooth and monotonic across all 200 levels.
    """
    level = clamp_level(level)
    anchors = DISTANCE_ANCHORS
    if level <= anchors[0][0]:
        return float(anchors[0][1])
    if level >= anchors[-1][0]:
        return float(anchors[-1][1])
    for (l0, d0), (l1, d1) in zip(anchors, anchors[1:]):
        if l0 <= level <= l1:
            if l1 == l0:
                return float(d0)
            t = (level - l0) / (l1 - l0)
            return d0 + (d1 - d0) * t
    return float(anchors[-1][1])


def speed_for(level: int) -> float:
    """Top speed for a level: the ceiling the in-run ramp climbs toward."""
    level = clamp_level(level)
    t = (level - 1) / max(1, MAX_LEVEL - 1)
    return SPEED_BASE + (SPEED_MAX - SPEED_BASE) * (t ** 0.85)


def start_speed_for(level: int) -> float:
    """Speed at the start of a run - always leaves room to accelerate."""
    cap = speed_for(level)
    return SPEED_BASE + (cap - SPEED_BASE) * 0.62


def bands_for(level: int) -> Dict[str, bool]:
    """Which mechanics have unlocked by this level."""
    level = clamp_level(level)
    return {
        "moving": level >= BAND_MOVING,
        "jumpy": level >= BAND_JUMPY,
        "fast": level >= BAND_FAST,
        "combo": level >= BAND_COMBO,
        "advanced": level >= BAND_ADVANCED,
        "veryfast": level >= BAND_VERYFAST,
        "extreme": level >= BAND_EXTREME,
    }


def kind_pool(level: int) -> Tuple[List[str], List[str]]:
    """(passable kinds, impassable kinds) unlocked at this level."""
    b = bands_for(level)
    passable = ["barrier", "bar"]
    if level >= 6:
        passable.append("pit")
    if b["jumpy"]:
        passable += ["pit", "wide_bar"]          # pit listed twice = more common
    if b["advanced"]:
        passable.append("wide_bar")

    impassable = ["block"]
    if b["moving"]:
        impassable.append("mover")
    if b["fast"]:
        impassable.append("train")
    if b["advanced"]:
        impassable += ["crusher", "train"]
    if b["extreme"]:
        impassable += ["mover", "crusher"]
    return passable, impassable


def level_name(level: int) -> str:
    level = clamp_level(level)
    if level == FINAL_LEVEL:
        return FINAL_LEVEL_NAME
    return f"LEVEL {level}"


def reward_for(level: int) -> int:
    """DOWN paid for a first clear."""
    level = clamp_level(level)
    if level == FINAL_LEVEL:
        return FINAL_LEVEL_REWARD
    return 120 + level * 26


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def _covered_lanes(lane: int, kind: str) -> Tuple[int, ...]:
    """Which lanes a placement occupies (wide_bar spans two)."""
    if obstacles.KINDS.get(kind, {}).get("lanes", 1) == 2:
        other = lane + 1 if lane < 2 else lane - 1
        return tuple(sorted((lane, other)))
    return (lane,)


class LevelPlan:
    """Everything about one level, generated once and reusable.

    ``rows`` is what obstacles.ObstacleField consumes:
    ``[(world_z, [(lane, kind), ...]), ...]``
    """

    def __init__(self, level: int) -> None:
        self.level = clamp_level(level)
        self.name = level_name(self.level)
        self.is_final = self.level == FINAL_LEVEL
        self.distance_m = distance_for(self.level)
        self.distance_units = self.distance_m * METER
        self.cap_speed = speed_for(self.level)
        self.start_speed = start_speed_for(self.level)
        self.bands = bands_for(self.level)
        self.world = world.world_for_level(self.level)
        self.reward = reward_for(self.level)

        rng = random.Random(self.level * 7919 + 13)
        self.rows: List[Tuple[float, List[Tuple[int, str]]]] = []
        self.coins: List[Tuple[float, int, float]] = []
        self.powerups: List[Tuple[float, int, str]] = []
        self._generate(rng)

        self.par_score = self._par_score()
        self.star2, self.star3 = int(self.par_score * 0.55), int(self.par_score * 0.82)

    # ------------------------------------------------------------- internals
    def _difficulty(self) -> float:
        return (self.level - 1) / max(1, MAX_LEVEL - 1)

    def _gap_time(self, rng: random.Random) -> float:
        """Seconds of road between rows. Tightens as levels climb."""
        t = self._difficulty()
        base = 1.35 - 0.67 * t
        return base * rng.uniform(0.88, 1.22)

    def _generate(self, rng: random.Random) -> None:
        t = self._difficulty()
        passable_pool, impassable_pool = kind_pool(self.level)
        limit = self.distance_units - END_CLEAR

        # How often the safe lane demands an action rather than being clear.
        action_chance = 0.34 + 0.42 * t
        # How likely the other two lanes are to be blocked.
        second_block = 0.18 + 0.62 * t
        third_block = (0.05 + 0.45 * t) if self.bands["combo"] else 0.0

        safe = 1
        z = FIRST_ROW
        prev_z = 0.0
        # World z after which each lane is clear of impassable obstacles.
        lane_block_until = [0.0, 0.0, 0.0]
        next_powerup = FIRST_ROW + POWERUP_SPACING * 0.5
        # The long run-up gives the first row a generous switching window.
        usable = FIRST_ROW / self.cap_speed

        while z < limit:
            # --- choose a safe lane that is genuinely reachable -------------
            # The switch must finish inside the window, so the player is never
            # still sliding between lanes when the row arrives.
            max_changes = max(1, int(usable / LANE_SWITCH_TIME))
            candidates = [
                l for l in range(3)
                if abs(l - safe) <= min(2, max_changes)
                and lane_block_until[l] <= prev_z + 1.0
            ]
            if not candidates:
                candidates = [safe]
            safe = rng.choice(candidates)

            row: List[Tuple[int, str]] = []
            needed_action = False

            # --- the safe lane: clear, or passable with the right action ----
            if rng.random() < action_chance:
                kind = rng.choice(passable_pool)
                if kind == "wide_bar":
                    # Anchor it so it definitely covers the safe lane.
                    row.append((safe if safe < 2 else 1, "wide_bar"))
                else:
                    row.append((safe, kind))
                needed_action = True

            # --- fill the other lanes with genuine blockers -----------------
            covered = set()
            for lane, kind in row:
                covered.update(_covered_lanes(lane, kind))
            others = [l for l in range(3) if l != safe and l not in covered]
            rng.shuffle(others)
            fills = 0
            if others and rng.random() < second_block:
                fills = 1
            if len(others) > 1 and rng.random() < third_block:
                fills = 2
            for lane in others[:fills]:
                kind = rng.choice(impassable_pool)
                row.append((lane, kind))
                lane_block_until[lane] = z + obstacles.KINDS[kind]["d"] * 0.5 + PLAYER_D

            if row:
                self.rows.append((z, row))

            # --- collectibles along the safe path --------------------------
            stretch = self.cap_speed * 0.75
            self._place_coins(rng, z, stretch, safe, row)
            if z >= next_powerup:
                kinds = tuple(POWERUP_BASE_TIME.keys())
                self.powerups.append((z + stretch * 0.5, safe, rng.choice(kinds)))
                next_powerup = z + POWERUP_SPACING

            # --- advance to the next row ------------------------------------
            gap_time = self._gap_time(rng)
            if needed_action:
                # Enough road to land or stand up before the next demand.
                gap_time = max(gap_time, 0.9)
            prev_z = z
            z += gap_time * self.cap_speed
            usable = gap_time * 0.5

        # Safety net: a level always has something to do.
        if not self.rows:
            self.rows.append((FIRST_ROW, [(1, "barrier")]))

    def _place_coins(self, rng: random.Random, z: float, stretch: float, safe: int,
                     row: Sequence[Tuple[int, str]]) -> None:
        """Coins reward staying on the safe line, and arc over jump hazards."""
        jump_kind = None
        for lane, kind in row:
            if kind in ("barrier", "pit") and safe in _covered_lanes(lane, kind):
                jump_kind = kind
                break

        if jump_kind:
            # An arc only a jump can collect.
            span = 5
            for i in range(span):
                frac = i / (span - 1)
                arc = 92.0 * (1.0 - (2.0 * frac - 1.0) ** 2)
                self.coins.append((z - 130.0 + i * 68.0, safe, max(18.0, arc)))

        # A straight run through the stretch after the row.
        count = rng.randint(4, 9)
        start = z + stretch * 0.3
        for i in range(count):
            self.coins.append((start + i * COIN_SPACING, safe, 34.0))

    def _par_score(self) -> int:
        """A clean, no-combo clear. Star thresholds are relative to this."""
        return int(
            self.distance_m * SCORE_PER_METER
            + len(self.coins) * SCORE_PER_COIN
            + len(self.powerups) * SCORE_PER_POWERUP
            + len(self.rows) * SCORE_PER_DODGE
        )

    # ---------------------------------------------------------------- public
    def stars_for(self, score: int) -> int:
        """1 star for finishing, 2 and 3 for score."""
        if score >= self.star3:
            return 3
        if score >= self.star2:
            return 2
        return 1

    def star_targets(self) -> Tuple[int, int, int]:
        return (0, self.star2, self.star3)

    def coin_total(self) -> int:
        return len(self.coins)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"<LevelPlan {self.level} {self.distance_m:.0f}m "
                f"rows={len(self.rows)} coins={len(self.coins)}>")


# --------------------------------------------------------------------------
# Cache - plans are pure functions of their level number.
# --------------------------------------------------------------------------

_PLANS: Dict[int, LevelPlan] = {}


def get_plan(level: int) -> LevelPlan:
    level = clamp_level(level)
    plan = _PLANS.get(level)
    if plan is None:
        plan = LevelPlan(level)
        if len(_PLANS) > 24:
            _PLANS.clear()
        _PLANS[level] = plan
    return plan
