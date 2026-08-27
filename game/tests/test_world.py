"""Tests for the projection, collision and world catalogue.

These need pygame's display and font subsystems, which conftest.py has already
pointed at the dummy drivers.
"""

from __future__ import annotations

import pytest

import camera
import obstacles
import voxel
import world as world_mod
from settings import (
    CAM_HEIGHT,
    CAM_Z,
    CX,
    FOCAL,
    HORIZON_Y,
    LANE_X,
    MAX_LEVEL,
    NEAR_Z,
    RARITY_PRICE,
)


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------


def test_scale_matches_the_documented_formula():
    assert camera.scale_at(0.0) == pytest.approx(FOCAL / CAM_Z)
    assert camera.scale_at(700.0) == pytest.approx(FOCAL / (700.0 + CAM_Z))


def test_scale_shrinks_with_distance_and_never_blows_up():
    assert camera.scale_at(0.0) > camera.scale_at(500.0) > camera.scale_at(4000.0)
    assert camera.scale_at(-CAM_Z) > 0.0          # the divide-by-zero guard
    assert camera.scale_at(-99999.0) > 0.0


def test_centre_of_the_road_projects_to_screen_centre():
    x, y, s = camera.project(0.0, 0.0, 0.0)
    assert x == pytest.approx(CX)
    assert y == pytest.approx(HORIZON_Y + CAM_HEIGHT * s)


def test_distant_points_converge_on_the_horizon():
    near = camera.ground_y(0.0)
    far = camera.ground_y(30_000.0)
    assert far < near
    assert far == pytest.approx(HORIZON_Y, abs=6.0)


def test_lanes_stay_ordered_left_to_right():
    for z in (0.0, 400.0, 2000.0):
        xs = [camera.screen_x(x, z) for x in LANE_X]
        assert xs == sorted(xs)


def test_draw_distance_grows_with_speed_and_is_capped():
    from settings import BASE_DRAW_Z, MAX_DRAW_Z

    assert camera.draw_z(0.0) == pytest.approx(BASE_DRAW_Z)
    assert camera.draw_z(600.0) > camera.draw_z(0.0)
    assert camera.draw_z(99999.0) == pytest.approx(MAX_DRAW_Z)


def test_fog_ramps_from_zero_to_one():
    far = 3000.0
    assert camera.fog_amount(0.0, far) == 0.0
    assert camera.fog_amount(far * 0.5, far) == 0.0
    assert 0.0 < camera.fog_amount(far * 0.8, far) < 1.0
    assert camera.fog_amount(far, far) == pytest.approx(1.0)
    assert camera.fog_amount(100.0, 0.0) == 0.0


# --------------------------------------------------------------------------
# Collision
# --------------------------------------------------------------------------


class _FakePlayer:
    """Just enough of Player for the AABB test."""

    def __init__(self, x=0.0, y=0.0, w=78.0, h=112.0, d=62.0):
        self._box = (x - w / 2, x + w / 2, y, y + h, -d / 2, d / 2)

    def hitbox(self):
        return self._box


def test_obstacle_in_the_same_lane_at_zero_depth_hits():
    obs = obstacles.Obstacle("block", 1, 0.0)
    assert obs.hits(_FakePlayer(x=LANE_X[1]).hitbox(), 0.0)


def test_obstacle_in_another_lane_misses():
    obs = obstacles.Obstacle("block", 0, 0.0)
    assert not obs.hits(_FakePlayer(x=LANE_X[2]).hitbox(), 0.0)


def test_obstacle_far_ahead_misses():
    obs = obstacles.Obstacle("block", 1, 2000.0)
    assert not obs.hits(_FakePlayer(x=LANE_X[1]).hitbox(), 0.0)


def test_jumping_clears_a_barrier():
    obs = obstacles.Obstacle("barrier", 1, 0.0)
    grounded = _FakePlayer(x=LANE_X[1], y=0.0)
    airborne = _FakePlayer(x=LANE_X[1], y=80.0)
    assert obs.hits(grounded.hitbox(), 0.0)
    assert not obs.hits(airborne.hitbox(), 0.0)


def test_sliding_clears_a_bar_but_standing_does_not():
    from settings import PLAYER_H, SLIDE_H_FACTOR

    obs = obstacles.Obstacle("bar", 1, 0.0)
    standing = _FakePlayer(x=LANE_X[1], h=PLAYER_H)
    sliding = _FakePlayer(x=LANE_X[1], h=PLAYER_H * SLIDE_H_FACTOR)
    assert obs.hits(standing.hitbox(), 0.0)
    assert not obs.hits(sliding.hitbox(), 0.0)


def test_wide_bar_covers_two_lanes():
    obs = obstacles.Obstacle("wide_bar", 0, 0.0)
    from settings import PLAYER_H

    for lane in (0, 1):
        assert obs.hits(_FakePlayer(x=LANE_X[lane], h=PLAYER_H).hitbox(), 0.0), lane


def test_travelled_shifts_depth():
    obs = obstacles.Obstacle("block", 1, 1000.0)
    box = _FakePlayer(x=LANE_X[1]).hitbox()
    assert not obs.hits(box, 0.0)
    assert obs.hits(box, 1000.0)


def test_mover_sweeps_but_stays_on_the_road():
    from settings import ROAD_HALF

    obs = obstacles.Obstacle("mover", 1, 500.0)
    seen = set()
    for i in range(60):
        obs.animate(i * 0.05)
        assert abs(obs.x) <= ROAD_HALF
        seen.add(round(obs.x))
    assert len(seen) > 5, "the mover never actually moved"


def test_crusher_oscillates_between_ground_and_lift():
    obs = obstacles.Obstacle("crusher", 1, 500.0)
    heights = []
    for i in range(80):
        obs.animate(i * 0.05)
        heights.append(obs.y0)
    assert min(heights) < 6.0
    assert max(heights) > obstacles.CRUSHER_LIFT * 0.85


# --------------------------------------------------------------------------
# Obstacle field
# --------------------------------------------------------------------------


def test_field_spawns_then_retires_rows():
    rows = [(1500.0, [(1, "barrier")]), (2500.0, [(0, "block")])]
    field = obstacles.ObstacleField(rows, {"main": (200, 80, 60)})
    assert field.active == []

    field.update(0.016, 800.0, 0.0, 0.0)
    assert field.active, "nothing spawned inside the draw distance"

    # Travel well past both rows.
    cleared_total = 0
    for _ in range(40):
        cleared_total += field.update(0.1, 800.0, 4000.0, 1.0)
    assert cleared_total == 2
    assert field.active == []
    assert field.remaining() == 0


def test_field_counts_a_dodge_but_not_a_hit():
    rows = [(400.0, [(1, "block")])]
    field = obstacles.ObstacleField(rows, {"main": (200, 80, 60)})
    field.update(0.016, 800.0, 0.0, 0.0)
    field.active[0].hit = True
    cleared = 0
    for _ in range(20):
        cleared += field.update(0.1, 800.0, 3000.0, 1.0)
    assert cleared == 0, "a hit obstacle must not count as dodged"


# --------------------------------------------------------------------------
# Worlds
# --------------------------------------------------------------------------


def test_there_are_eight_worlds_covering_every_level():
    assert len(world_mod.WORLDS) == 8
    assert world_mod.LEVELS_PER_WORLD * len(world_mod.WORLDS) == MAX_LEVEL
    for lvl in range(1, MAX_LEVEL + 1):
        assert world_mod.world_for_level(lvl) in world_mod.WORLDS


def test_world_boundaries_land_where_expected():
    assert world_mod.world_for_level(1)["id"] == "green_valley"
    assert world_mod.world_for_level(25)["id"] == "green_valley"
    assert world_mod.world_for_level(26)["id"] == "desert_dunes"
    assert world_mod.world_for_level(200)["id"] == "sky_temple"
    assert world_mod.first_level_of("desert_dunes") == 26


def test_starter_world_is_free_and_others_are_priced():
    assert world_mod.WORLDS[0]["price"] == 0
    for spec in world_mod.WORLDS[1:]:
        assert spec["price"] == RARITY_PRICE[spec["rarity"]]


def test_every_world_defines_the_keys_the_renderer_reads():
    needed = ("sky_top", "sky_bottom", "haze", "ground", "road_a", "road_b",
              "stripe", "edge", "verge_a", "verge_b", "props", "prop_palette",
              "obstacle", "name", "rarity")
    for spec in world_mod.WORLDS:
        for key in needed:
            assert key in spec, f"{spec['id']} is missing {key}"
        for key in ("main", "accent", "metal"):
            assert key in spec["obstacle"], f"{spec['id']} obstacle palette needs {key}"
        for kind in spec["props"]:
            assert kind in voxel.SCENERY_KINDS, f"{spec['id']} uses unknown prop {kind}"


def test_resolve_world_respects_ownership_and_auto(save):
    # Auto on, themed world not owned -> falls back to the starter.
    save.data["world_auto"] = True
    assert world_mod.resolve_world(save, 200)["id"] == "green_valley"

    save.add_world("sky_temple")
    assert world_mod.resolve_world(save, 200)["id"] == "sky_temple"

    # Auto off -> the manual choice wins.
    save.data["world_auto"] = False
    save.data["world"] = "green_valley"
    assert world_mod.resolve_world(save, 200)["id"] == "green_valley"

    # An unowned manual choice still cannot leak through.
    save.data["world"] = "cyber_city"
    assert world_mod.resolve_world(save, 200)["id"] == "green_valley"
