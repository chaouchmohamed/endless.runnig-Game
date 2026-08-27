"""
world.py - The eight worlds of BLOCK ADVENTURE and the road that runs through them.

A world is pure data: two sky colours, a horizon haze, two alternating road
bands, a verge, and a roadside prop set with its own three-colour palette. That
is enough for eight visually distinct places out of one renderer.

The road is drawn as a stack of depth bands (``STRIPE_LEN`` long each), far to
near. Alternating the band shade is what actually sells speed - the bands stream
toward the camera even when nothing else on screen moves.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

import camera
import voxel
from settings import (
    HEIGHT,
    HORIZON_Y,
    LANE_W,
    MAX_LEVEL,
    NEAR_Z,
    RARITY_PRICE,
    ROAD_HALF,
    SHOULDER,
    STRIPE_LEN,
    WIDTH,
)

# --------------------------------------------------------------------------
# World catalogue
#
# Each world owns 25 of the 200 levels (see world_for_level), and its price
# comes from its rarity - except the starter valley, which is always free
# because save_system defaults every profile to owning it.
# --------------------------------------------------------------------------

WORLDS: List[dict] = [
    {
        "id": "green_valley", "name": "Green Valley", "rarity": "COMMON",
        "desc": "Rolling meadows where every adventure begins.",
        "sky_top": (74, 152, 226), "sky_bottom": (168, 214, 246),
        "haze": (196, 224, 240), "ground": (96, 168, 96),
        "road_a": (108, 114, 128), "road_b": (96, 102, 116),
        "stripe": (238, 238, 226), "edge": (208, 212, 220),
        "verge_a": (110, 184, 104), "verge_b": (94, 166, 92),
        "sun": (255, 244, 190), "sun_at": (0.74, 0.30), "clouds": (255, 255, 255),
        "props": ("tree", "pine", "rock", "mushroom"),
        "prop_palette": {"prop_a": (124, 92, 56), "prop_b": (84, 162, 82),
                         "prop_c": (226, 240, 170)},
        "obstacle": {"main": (198, 84, 72), "accent": (250, 226, 150),
                     "metal": (176, 184, 202)},
    },
    {
        "id": "desert_dunes", "name": "Desert Dunes", "rarity": "COMMON",
        "desc": "Endless sand and a sun that never blinks.",
        "sky_top": (246, 170, 96), "sky_bottom": (252, 224, 168),
        "haze": (250, 226, 178), "ground": (226, 188, 124),
        "road_a": (198, 166, 116), "road_b": (184, 152, 104),
        "stripe": (252, 240, 210), "edge": (222, 196, 148),
        "verge_a": (232, 198, 134), "verge_b": (214, 180, 118),
        "sun": (255, 246, 206), "sun_at": (0.5, 0.22), "clouds": None,
        "props": ("cactus", "rock", "ruin", "spike"),
        "prop_palette": {"prop_a": (170, 130, 84), "prop_b": (108, 158, 92),
                         "prop_c": (255, 232, 168)},
        "obstacle": {"main": (176, 108, 62), "accent": (255, 226, 158),
                     "metal": (198, 186, 168)},
    },
    {
        "id": "snow_peaks", "name": "Snow Peaks", "rarity": "UNCOMMON",
        "desc": "Thin air, deep drifts, sharper turns.",
        "sky_top": (128, 174, 216), "sky_bottom": (216, 234, 248),
        "haze": (232, 242, 252), "ground": (236, 244, 252),
        "road_a": (176, 192, 210), "road_b": (162, 178, 198),
        "stripe": (255, 255, 255), "edge": (204, 220, 236),
        "verge_a": (240, 248, 255), "verge_b": (222, 234, 246),
        "sun": (240, 250, 255), "sun_at": (0.26, 0.26), "clouds": (255, 255, 255),
        "props": ("pine", "spike", "rock"),
        "prop_palette": {"prop_a": (108, 96, 88), "prop_b": (72, 128, 110),
                         "prop_c": (204, 236, 255)},
        "obstacle": {"main": (96, 158, 206), "accent": (232, 248, 255),
                     "metal": (188, 202, 220)},
    },
    {
        "id": "jungle_ruins", "name": "Jungle Ruins", "rarity": "UNCOMMON",
        "desc": "Old stone, new vines, no mercy.",
        "sky_top": (36, 104, 96), "sky_bottom": (108, 176, 140),
        "haze": (150, 198, 168), "ground": (58, 116, 70),
        "road_a": (110, 122, 100), "road_b": (98, 110, 90),
        "stripe": (214, 226, 190), "edge": (146, 160, 128),
        "verge_a": (72, 134, 82), "verge_b": (60, 118, 72),
        "sun": (216, 246, 200), "sun_at": (0.62, 0.34), "clouds": (206, 230, 214),
        "props": ("tree", "pillar", "ruin", "mushroom"),
        "prop_palette": {"prop_a": (146, 142, 118), "prop_b": (62, 140, 84),
                         "prop_c": (238, 226, 140)},
        "obstacle": {"main": (146, 122, 78), "accent": (206, 232, 158),
                     "metal": (158, 164, 148)},
    },
    {
        "id": "lava_caves", "name": "Lava Caves", "rarity": "RARE",
        "desc": "The floor glows. Keep moving.",
        "sky_top": (30, 14, 18), "sky_bottom": (128, 40, 26),
        "haze": (158, 62, 32), "ground": (62, 30, 26),
        "road_a": (66, 46, 44), "road_b": (54, 38, 38),
        "stripe": (255, 168, 72), "edge": (150, 70, 40),
        "verge_a": (86, 40, 32), "verge_b": (70, 32, 26),
        "sun": (255, 138, 54), "sun_at": (0.5, 0.38), "clouds": None,
        "props": ("spike", "rock", "crystal"),
        "prop_palette": {"prop_a": (78, 48, 44), "prop_b": (196, 74, 38),
                         "prop_c": (255, 156, 54)},
        "obstacle": {"main": (168, 62, 44), "accent": (255, 178, 78),
                     "metal": (146, 130, 124)},
    },
    {
        "id": "crystal_caverns", "name": "Crystal Caverns", "rarity": "EPIC",
        "desc": "Light bends. So does the road.",
        "sky_top": (26, 18, 52), "sky_bottom": (86, 62, 148),
        "haze": (128, 106, 196), "ground": (54, 42, 92),
        "road_a": (74, 64, 112), "road_b": (62, 54, 98),
        "stripe": (196, 176, 255), "edge": (128, 112, 190),
        "verge_a": (84, 68, 132), "verge_b": (70, 56, 114),
        "sun": (198, 176, 255), "sun_at": (0.38, 0.24), "clouds": None,
        "props": ("crystal", "pillar", "spike"),
        "prop_palette": {"prop_a": (96, 84, 146), "prop_b": (150, 126, 240),
                         "prop_c": (216, 200, 255)},
        "obstacle": {"main": (132, 100, 216), "accent": (224, 208, 255),
                     "metal": (168, 176, 208)},
    },
    {
        "id": "cyber_city", "name": "Cyber City", "rarity": "LEGENDARY",
        "desc": "Neon, rain, and a very fast road.",
        "sky_top": (12, 16, 36), "sky_bottom": (34, 44, 92),
        "haze": (56, 82, 148), "ground": (22, 28, 52),
        "road_a": (40, 48, 78), "road_b": (32, 40, 68),
        "stripe": (94, 246, 226), "edge": (78, 132, 200),
        "verge_a": (30, 38, 68), "verge_b": (24, 32, 58),
        "sun": None, "sun_at": (0.5, 0.2), "clouds": (48, 62, 112),
        "props": ("sign", "lamp", "pillar"),
        "prop_palette": {"prop_a": (56, 64, 96), "prop_b": (255, 92, 178),
                         "prop_c": (94, 246, 226)},
        "obstacle": {"main": (58, 72, 122), "accent": (94, 246, 226),
                     "metal": (186, 198, 224)},
    },
    {
        "id": "sky_temple", "name": "Sky Temple", "rarity": "MYTHIC",
        "desc": "Above the clouds, where the final adventure waits.",
        "sky_top": (128, 186, 246), "sky_bottom": (250, 232, 196),
        "haze": (255, 244, 214), "ground": (226, 232, 246),
        "road_a": (232, 224, 202), "road_b": (218, 208, 186),
        "stripe": (255, 214, 120), "edge": (240, 226, 190),
        "verge_a": (246, 240, 224), "verge_b": (232, 224, 206),
        "sun": (255, 250, 224), "sun_at": (0.5, 0.18), "clouds": (255, 255, 255),
        "props": ("pillar", "crystal", "ruin"),
        "prop_palette": {"prop_a": (232, 222, 198), "prop_b": (255, 206, 96),
                         "prop_c": (255, 246, 210)},
        "obstacle": {"main": (206, 168, 92), "accent": (255, 246, 210),
                     "metal": (226, 232, 244)},
    },
]

for _w in WORLDS:
    _w.setdefault("price", RARITY_PRICE[_w["rarity"]])
WORLDS[0]["price"] = 0                      # the starter world is always owned

WORLDS_BY_ID: Dict[str, dict] = {w["id"]: w for w in WORLDS}
LEVELS_PER_WORLD = max(1, MAX_LEVEL // len(WORLDS))


def get_world(wid: str) -> dict:
    return WORLDS_BY_ID.get(wid) or WORLDS[0]


def world_for_level(level: int) -> dict:
    """Levels 1-25 -> world 1, 26-50 -> world 2, and so on."""
    idx = (max(1, int(level)) - 1) // LEVELS_PER_WORLD
    return WORLDS[min(len(WORLDS) - 1, idx)]


def world_index(wid: str) -> int:
    for i, w in enumerate(WORLDS):
        if w["id"] == wid:
            return i
    return 0


def first_level_of(wid: str) -> int:
    return world_index(wid) * LEVELS_PER_WORLD + 1


def resolve_world(save, level: int) -> dict:
    """Which world to actually render.

    With ``world_auto`` on, a level shows its own themed world when the player
    owns it, so progressing through the game visibly changes scenery. Otherwise
    (or when the theme is not owned) the manual choice is used.
    """
    themed = world_for_level(level)
    if save.data.get("world_auto", True) and save.owns_world(themed["id"]):
        return themed
    chosen = get_world(save.data.get("world", "green_valley"))
    if not save.owns_world(chosen["id"]):
        return WORLDS[0]
    return chosen


# --------------------------------------------------------------------------
# Sky
# --------------------------------------------------------------------------


def _gradient(w: int, h: int, top: Sequence[int], bottom: Sequence[int]) -> pygame.Surface:
    surf = pygame.Surface((1, max(1, h)))
    for y in range(max(1, h)):
        surf.set_at((0, y), voxel.mix(top, bottom, y / max(1, h - 1)))
    return pygame.transform.scale(surf, (w, max(1, h)))


def sky_surface(spec: dict) -> pygame.Surface:
    key = f"sky:{spec['id']}"
    sky_h = int(HORIZON_Y) + 2

    def build() -> pygame.Surface:
        surf = pygame.Surface((WIDTH, sky_h))
        surf.blit(_gradient(WIDTH, sky_h, spec["sky_top"], spec["sky_bottom"]), (0, 0))
        sun = spec.get("sun")
        if sun:
            fx, fy = spec.get("sun_at", (0.7, 0.3))
            cx, cy = int(WIDTH * fx), int(sky_h * fy)
            glow = pygame.Surface((WIDTH, sky_h), pygame.SRCALPHA)
            for r, a in ((190, 26), (140, 34), (96, 48)):
                pygame.draw.circle(glow, voxel.with_alpha(sun, a), (cx, cy), r)
            surf.blit(glow, (0, 0))
            pygame.draw.circle(surf, sun, (cx, cy), 44)
            pygame.draw.circle(surf, voxel.lighten(sun, 0.5), (cx, cy), 34)
        return surf

    return voxel.CACHE.base(key, build)


def ground_surface(spec: dict) -> pygame.Surface:
    """Everything below the horizon, hazing out as it recedes."""
    key = f"ground:{spec['id']}"
    gh = HEIGHT - int(HORIZON_Y) + 2

    def build() -> pygame.Surface:
        return _gradient(WIDTH, gh, spec["haze"], spec["ground"])

    return voxel.CACHE.base(key, build)


def _cloud_surface(color: Sequence[int], index: int) -> pygame.Surface:
    key = f"cloud:{index}:{int(color[0])}"

    def build() -> pygame.Surface:
        w, h = 220, 78
        s = voxel.make_surface(w, h)
        rng = random.Random(index * 7919)
        for _ in range(6):
            cw = rng.randint(60, 120)
            ch = rng.randint(30, 54)
            cx = rng.randint(0, w - cw)
            cy = rng.randint(0, h - ch)
            pygame.draw.ellipse(s, voxel.with_alpha(color, 150), (cx, cy, cw, ch))
        return s

    return voxel.CACHE.base(key, build)


# --------------------------------------------------------------------------
# Roadside props
# --------------------------------------------------------------------------


class Prop:
    """One billboard sitting on the verge."""

    __slots__ = ("kind", "x", "z", "h")

    def __init__(self, kind: str, x: float, z: float, h: float) -> None:
        self.kind = kind
        self.x = x
        self.z = z
        self.h = h


class WorldRenderer:
    """Draws one world, and owns the rolling list of roadside props."""

    PROP_GAP = 260.0              # world units between prop spawns per side

    def __init__(self, spec: dict, seed: int = 0) -> None:
        self.spec = spec
        self.rng = random.Random(seed or 1234)
        self.props: List[Prop] = []
        self.cloud_shift = 0.0
        self._next_prop = 0.0
        self.reset()

    # ----------------------------------------------------------------- state
    def set_world(self, spec: dict) -> None:
        if spec["id"] != self.spec["id"]:
            self.spec = spec
            self.reset()

    def reset(self) -> None:
        self.props.clear()
        self.cloud_shift = 0.0
        self._next_prop = 0.0
        # Pre-populate so the road never starts bare.
        z = 200.0
        while z < 3200.0:
            self._spawn_prop(z)
            z += self.PROP_GAP * self.rng.uniform(0.7, 1.4)

    def _spawn_prop(self, z: float) -> None:
        spec = self.spec
        kinds = spec.get("props") or ("rock",)
        for side in (-1, 1):
            if self.rng.random() < 0.32:
                continue
            kind = self.rng.choice(kinds)
            off = ROAD_HALF + SHOULDER * self.rng.uniform(0.28, 1.5)
            x = side * off
            h = self.rng.uniform(180.0, 340.0)
            if kind in ("rock", "mushroom"):
                h *= 0.55
            self.props.append(Prop(kind, x, z + self.rng.uniform(-60.0, 60.0), h))

    # ---------------------------------------------------------------- update
    def update(self, dt: float, speed: float, travelled: float) -> None:
        move = speed * dt
        self.cloud_shift += move * 0.012
        far = camera.draw_z(speed)

        for prop in self.props:
            prop.z -= move
        if self.props:
            self.props = [p for p in self.props if p.z > NEAR_Z - 200.0]

        # Keep the far end stocked.
        furthest = max((p.z for p in self.props), default=0.0)
        guard = 0
        while furthest < far + 400.0 and guard < 40:
            step = self.PROP_GAP * self.rng.uniform(0.7, 1.4)
            furthest += step
            self._spawn_prop(furthest)
            guard += 1

    # ------------------------------------------------------------------ draw
    def draw_background(self, surf: pygame.Surface, shake: Tuple[float, float] = (0.0, 0.0)) -> None:
        spec = self.spec
        sy = shake[1] * 0.35
        surf.blit(sky_surface(spec), (0, sy - 2))
        surf.blit(ground_surface(spec), (0, HORIZON_Y + sy - 2))

        clouds = spec.get("clouds")
        if clouds:
            for i in range(4):
                cs = _cloud_surface(clouds, i)
                cw = cs.get_width()
                span = WIDTH + cw
                x = (-self.cloud_shift * (0.5 + i * 0.22) + i * 340.0) % span - cw
                y = 26 + i * 34 + sy * 0.5
                surf.blit(cs, (x, y))

    def draw_road(self, surf: pygame.Surface, travelled: float, speed: float,
                  shake: Tuple[float, float] = (0.0, 0.0)) -> None:
        """Depth bands, far to near, so nearer bands overdraw the seams."""
        spec = self.spec
        far = camera.draw_z(speed)
        haze = spec["haze"]
        sx, sy = shake

        first = int(math.floor((travelled + NEAR_Z) / STRIPE_LEN))
        last = int(math.ceil((travelled + far) / STRIPE_LEN))
        lane_edges = (-LANE_W * 0.5, LANE_W * 0.5)

        for band in range(last, first - 1, -1):
            z_near = band * STRIPE_LEN - travelled
            z_far = z_near + STRIPE_LEN
            if z_far <= NEAR_Z or z_near >= far:
                continue
            z_near = max(z_near, NEAR_Z)
            z_far = min(z_far, far)
            if z_far - z_near < 0.5:
                continue

            yn = camera.ground_y(z_near) + sy
            yf = camera.ground_y(z_far) + sy
            fog = camera.fog_amount((z_near + z_far) * 0.5, far)
            even = band % 2 == 0

            def px(x: float, z: float) -> float:
                return camera.screen_x(x, z) + sx

            # Verges either side of the road.
            verge = spec["verge_a"] if even else spec["verge_b"]
            for side in (-1, 1):
                inner = side * ROAD_HALF
                outer = side * (ROAD_HALF + SHOULDER)
                voxel.quad(surf, [
                    (px(inner, z_far), yf), (px(outer, z_far), yf),
                    (px(outer, z_near), yn), (px(inner, z_near), yn),
                ], verge, face="front", outline=False, fog=fog, fog_color=haze)

            # Road surface.
            road = spec["road_a"] if even else spec["road_b"]
            voxel.quad(surf, [
                (px(-ROAD_HALF, z_far), yf), (px(ROAD_HALF, z_far), yf),
                (px(ROAD_HALF, z_near), yn), (px(-ROAD_HALF, z_near), yn),
            ], road, face="front", outline=False, fog=fog, fog_color=haze)

            # Solid edge lines.
            for side in (-1, 1):
                a = side * (ROAD_HALF - 10.0)
                b = side * ROAD_HALF
                voxel.quad(surf, [
                    (px(a, z_far), yf), (px(b, z_far), yf),
                    (px(b, z_near), yn), (px(a, z_near), yn),
                ], spec["edge"], face="front", outline=False, fog=fog, fog_color=haze)

            # Dashed lane dividers - only on even bands, which makes the dashes.
            if even:
                for edge in lane_edges:
                    voxel.quad(surf, [
                        (px(edge - 4.0, z_far), yf), (px(edge + 4.0, z_far), yf),
                        (px(edge + 4.0, z_near), yn), (px(edge - 4.0, z_near), yn),
                    ], spec["stripe"], face="front", outline=False, fog=fog, fog_color=haze)

    def draw_props(self, surf: pygame.Surface, speed: float,
                   shake: Tuple[float, float] = (0.0, 0.0)) -> None:
        spec = self.spec
        far = camera.draw_z(speed)
        palette = spec.get("prop_palette", {})
        ratio = voxel.scenery_ratio()
        sx, sy = shake

        for prop in sorted(self.props, key=lambda p: -p.z):
            if prop.z <= NEAR_Z or prop.z > far:
                continue
            scale = camera.scale_at(prop.z)
            h = int(prop.h * scale)
            if h < 6:
                continue
            w = max(4, int(h / ratio))
            if w > WIDTH * 2:
                continue
            px = camera.screen_x(prop.x, prop.z) + sx
            if px < -w or px > WIDTH + w:
                continue
            sprite = voxel.scenery_sprite(prop.kind, spec["id"], palette, w, h)
            base_y = camera.ground_y(prop.z) + sy
            surf.blit(sprite, (px - w / 2, base_y - h))

    def draw(self, surf: pygame.Surface, travelled: float, speed: float,
             shake: Tuple[float, float] = (0.0, 0.0)) -> None:
        self.draw_background(surf, shake)
        self.draw_road(surf, travelled, speed, shake)
        self.draw_props(surf, speed, shake)


# --------------------------------------------------------------------------
# Menu backdrop
# --------------------------------------------------------------------------


class MenuBackdrop:
    """A slow, endless road used behind the menus so nothing feels static."""

    def __init__(self, spec: dict) -> None:
        self.renderer = WorldRenderer(spec, seed=99)
        self.travelled = 0.0
        self.speed = 340.0

    def set_world(self, spec: dict) -> None:
        self.renderer.set_world(spec)

    def update(self, dt: float) -> None:
        self.travelled += self.speed * dt
        self.renderer.update(dt, self.speed, self.travelled)

    def draw(self, surf: pygame.Surface) -> None:
        self.renderer.draw(surf, self.travelled, self.speed)
