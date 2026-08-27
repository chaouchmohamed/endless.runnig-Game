"""
voxel.py - Original voxel/blocky art generated at runtime with Pygame.

Nothing here loads external art. Every character, obstacle, coin and power-up is
built out of shaded cubes, which gives the game a consistent blocky look and
keeps the project free of third-party assets.

Two ideas carry the whole renderer:

* ``cube()`` draws one block as three faces (front, lit top, shaded side).
  Stacking cubes is enough to build anything the game needs.
* ``SpriteCache`` renders a model once at a base resolution and then keeps
  nearest-neighbour scaled copies, so perspective scaling costs almost nothing
  and the art stays crisp and pixel-blocky instead of blurry.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Sequence, Tuple

import pygame

Color = Tuple[int, int, int]

# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------


def clamp(value: float, low: float = 0.0, high: float = 255.0) -> int:
    return int(max(low, min(high, value)))


def shade(color: Sequence[int], factor: float) -> Color:
    """Multiply brightness. factor > 1 lightens, < 1 darkens."""
    return (clamp(color[0] * factor), clamp(color[1] * factor), clamp(color[2] * factor))


def mix(a: Sequence[int], b: Sequence[int], t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (
        clamp(a[0] + (b[0] - a[0]) * t),
        clamp(a[1] + (b[1] - a[1]) * t),
        clamp(a[2] + (b[2] - a[2]) * t),
    )


def lighten(color: Sequence[int], amount: float) -> Color:
    return mix(color, (255, 255, 255), amount)


def darken(color: Sequence[int], amount: float) -> Color:
    return mix(color, (0, 0, 0), amount)


def with_alpha(color: Sequence[int], alpha: int) -> Tuple[int, int, int, int]:
    return (int(color[0]), int(color[1]), int(color[2]), int(alpha))


# --------------------------------------------------------------------------
# Cube drawing
# --------------------------------------------------------------------------

TOP_LIGHT = 1.30
SIDE_DARK = 0.66


def cube(
    surf: pygame.Surface,
    x: float,
    y: float,
    w: float,
    h: float,
    color: Sequence[int],
    depth: float | None = None,
    top: bool = True,
    side: int = 1,
    outline: bool = True,
) -> None:
    """Draw one voxel block.

    ``x, y`` is the top-left of the *front* face. ``side`` is +1 to reveal the
    right-hand face, -1 for the left, 0 for none. ``depth`` defaults to a
    proportion of the block size so models look consistent at any scale.
    """
    x, y, w, h = int(x), int(y), max(1, int(w)), max(1, int(h))
    if depth is None:
        depth = max(2.0, min(w, h) * 0.34)
    d = int(depth)
    base = (int(color[0]), int(color[1]), int(color[2]))

    if top and d > 0:
        pygame.draw.polygon(
            surf,
            shade(base, TOP_LIGHT),
            [(x, y), (x + w, y), (x + w + d * side, y - d), (x + d * side, y - d)],
        )
    if side and d > 0:
        if side > 0:
            pts = [(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)]
        else:
            pts = [(x, y), (x - d, y - d), (x - d, y + h - d), (x, y + h)]
        pygame.draw.polygon(surf, shade(base, SIDE_DARK), pts)

    pygame.draw.rect(surf, base, (x, y, w, h))
    if outline and w > 3 and h > 3:
        pygame.draw.rect(surf, darken(base, 0.45), (x, y, w, h), 1)


def stud(surf: pygame.Surface, x: float, y: float, w: float, h: float, color: Sequence[int]) -> None:
    """A flat detail block (no 3D faces) - used for eyes, runes, stripes."""
    pygame.draw.rect(surf, (int(color[0]), int(color[1]), int(color[2])),
                     (int(x), int(y), max(1, int(w)), max(1, int(h))))


def make_surface(w: int, h: int) -> pygame.Surface:
    return pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)


# --------------------------------------------------------------------------
# Sprite cache
# --------------------------------------------------------------------------


class SpriteCache:
    """Builds a base sprite once, then hands out scaled copies.

    Scaled sizes are quantised (``STEP`` px) so a smoothly approaching obstacle
    reuses a handful of surfaces instead of allocating a new one every frame.
    """

    STEP = 4
    MAX_SCALED = 1400

    def __init__(self) -> None:
        self._base: Dict[str, pygame.Surface] = {}
        self._scaled: Dict[Tuple[str, int, int], pygame.Surface] = {}

    def base(self, key: str, builder: Callable[[], pygame.Surface]) -> pygame.Surface:
        surf = self._base.get(key)
        if surf is None:
            surf = builder()
            self._base[key] = surf
        return surf

    def scaled(
        self,
        key: str,
        builder: Callable[[], pygame.Surface],
        width: float,
        height: float,
    ) -> pygame.Surface:
        base = self.base(key, builder)
        step = self.STEP
        w = max(2, int(round(width / step)) * step)
        h = max(2, int(round(height / step)) * step)
        if w == base.get_width() and h == base.get_height():
            return base
        ck = (key, w, h)
        surf = self._scaled.get(ck)
        if surf is None:
            if len(self._scaled) > self.MAX_SCALED:
                self._scaled.clear()
            surf = pygame.transform.scale(base, (w, h))
            self._scaled[ck] = surf
        return surf

    def clear(self) -> None:
        self._base.clear()
        self._scaled.clear()

    def stats(self) -> Tuple[int, int]:
        return len(self._base), len(self._scaled)


CACHE = SpriteCache()


# --------------------------------------------------------------------------
# Characters
#
# A character spec is plain data (see CHARACTERS in player.py) so new blocky
# heroes are a few lines of colour. Frames are drawn facing away from the
# camera, which is what an endless runner needs.
# --------------------------------------------------------------------------

CHAR_W = 104
CHAR_H = 132


def _hair_or_helmet(surf: pygame.Surface, spec: dict, hx: int, hy: int, hw: int, hh: int) -> None:
    style = spec.get("head_style", "plain")
    accent = spec.get("accent", (200, 200, 200))
    if style == "helmet":
        cube(surf, hx - 2, hy - 3, hw + 4, hh // 2 + 3, accent, depth=4)
        stud(surf, hx + 2, hy + hh // 2, hw - 4, 3, darken(accent, 0.3))
    elif style == "hood":
        cube(surf, hx - 3, hy - 3, hw + 6, hh - 2, accent, depth=4)
        stud(surf, hx + 3, hy + 5, hw - 6, hh - 9, darken(spec.get("skin", (60, 60, 60)), 0.55))
    elif style == "crown":
        cube(surf, hx, hy - 7, hw, 6, (255, 206, 74), depth=3)
        for i in range(3):
            stud(surf, hx + 2 + i * (hw // 3), hy - 12, 4, 6, (255, 226, 120))
            stud(surf, hx + 3 + i * (hw // 3), hy - 14, 2, 3, (255, 120, 160))
    elif style == "horns":
        cube(surf, hx - 6, hy - 4, 6, 10, accent, depth=3)
        cube(surf, hx + hw, hy - 4, 6, 10, accent, depth=3)
        cube(surf, hx, hy - 2, hw, 6, darken(accent, 0.2), depth=3)
    elif style == "visor":
        stud(surf, hx - 1, hy + 8, hw + 2, 8, accent)
        stud(surf, hx + 1, hy + 10, hw - 2, 4, lighten(accent, 0.55))
    elif style == "halo":
        pygame.draw.ellipse(surf, (255, 240, 160), (hx - 4, hy - 12, hw + 8, 7), 3)
    elif style == "hat":
        cube(surf, hx - 5, hy - 6, hw + 10, 5, accent, depth=3)
        cube(surf, hx + 2, hy - 14, hw - 4, 9, darken(accent, 0.15), depth=3)
    elif style == "hair":
        cube(surf, hx - 1, hy - 2, hw + 2, 9, accent, depth=3)
    elif style == "band":
        stud(surf, hx - 2, hy + 6, hw + 4, 5, accent)
        stud(surf, hx + hw, hy + 7, 8, 3, accent)


def _character_frame(spec: dict, pose: str, phase: float) -> pygame.Surface:
    """Draw one animation frame of a blocky runner, seen from behind."""
    surf = make_surface(CHAR_W, CHAR_H)
    skin = spec.get("skin", (232, 190, 150))
    shirt = spec.get("shirt", (70, 140, 220))
    pants = spec.get("pants", (60, 68, 92))
    shoes = spec.get("shoes", (46, 40, 38))
    accent = spec.get("accent", (250, 220, 120))
    glow = spec.get("glow")

    cx = CHAR_W // 2
    swing = math.sin(phase * math.tau)
    swing2 = math.sin(phase * math.tau + math.pi)
    bob = int(abs(math.sin(phase * math.tau)) * 3)

    if pose == "slide":
        # Lying back, feet first: short and wide.
        base_y = 96
        cube(surf, cx - 34, base_y - 6, 44, 26, shirt, depth=7)                    # torso
        cube(surf, cx - 42, base_y - 2, 12, 18, skin, depth=5)                     # head
        _hair_or_helmet(surf, spec, cx - 42, base_y - 2, 12, 18)
        cube(surf, cx + 8, base_y - 2, 24, 12, pants, depth=6)                     # legs
        cube(surf, cx + 30, base_y + 2, 10, 10, shoes, depth=4)
        cube(surf, cx - 20, base_y + 18, 30, 9, shade(shirt, 0.8), depth=4)        # trailing arm
        if glow:
            pygame.draw.rect(surf, with_alpha(glow, 90), (cx - 40, base_y - 10, 80, 40), 2)
        return surf

    if pose == "jump":
        leg_a, leg_b = -14, -4
        arm_a, arm_b = -16, -10
        bob = 0
    elif pose == "hit":
        leg_a, leg_b = 2, 2
        arm_a, arm_b = -18, -18
    else:
        leg_a = int(swing * 13)
        leg_b = int(swing2 * 13)
        arm_a = int(swing2 * 12)
        arm_b = int(swing * 12)

    top = 14 + bob

    # Legs (drawn first so the torso overlaps them)
    for dx, off, mirror in ((-13, leg_a, -1), (5, leg_b, 1)):
        ly = 92 + bob - max(0, off) // 2
        lh = 34 - abs(off) // 3
        cube(surf, cx + dx, ly - off // 2, 15, lh, pants, depth=5, side=mirror)
        cube(surf, cx + dx - 1, ly - off // 2 + lh - 2, 17, 9, shoes, depth=4, side=mirror)

    # Arms
    for dx, off, mirror in ((-27, arm_a, -1), (20, arm_b, 1)):
        cube(surf, cx + dx, 46 + bob + off // 3, 12, 33, shade(shirt, 0.86),
             depth=4, side=mirror)
        cube(surf, cx + dx, 46 + bob + off // 3 + 31, 12, 8, skin, depth=4, side=mirror)

    # Torso
    cube(surf, cx - 20, 44 + bob, 40, 50, shirt, depth=7)
    if spec.get("chest_stripe", True):
        stud(surf, cx - 16, 60 + bob, 32, 5, accent)
    if spec.get("belt", True):
        stud(surf, cx - 20, 86 + bob, 40, 6, darken(pants, 0.25))

    # Cape / wings sit behind the shoulders
    if spec.get("cape"):
        cape_c = spec.get("cape")
        wave = int(swing * 4)
        pygame.draw.polygon(
            surf, cape_c,
            [(cx - 22, 48 + bob), (cx + 22, 48 + bob),
             (cx + 18 + wave, 104 + bob), (cx - 18 + wave, 104 + bob)],
        )
        pygame.draw.polygon(
            surf, darken(cape_c, 0.3),
            [(cx - 22, 48 + bob), (cx + 22, 48 + bob),
             (cx + 22, 56 + bob), (cx - 22, 56 + bob)],
        )
    if spec.get("wings"):
        wc = spec.get("wings")
        flap = int(swing * 6)
        for sgn in (-1, 1):
            pygame.draw.polygon(
                surf, wc,
                [(cx + sgn * 18, 50 + bob),
                 (cx + sgn * 46, 34 + bob - flap),
                 (cx + sgn * 44, 62 + bob - flap),
                 (cx + sgn * 20, 74 + bob)],
            )
            pygame.draw.polygon(
                surf, darken(wc, 0.35),
                [(cx + sgn * 18, 50 + bob),
                 (cx + sgn * 46, 34 + bob - flap),
                 (cx + sgn * 44, 62 + bob - flap),
                 (cx + sgn * 20, 74 + bob)], 1,
            )

    # Head
    hw, hh = 34, 30
    hx, hy = cx - hw // 2, top
    cube(surf, hx, hy, hw, hh, skin, depth=7)
    stud(surf, hx + 4, hy + hh - 6, hw - 8, 4, darken(skin, 0.25))   # nape shadow
    _hair_or_helmet(surf, spec, hx, hy, hw, hh)

    if spec.get("backpack"):
        cube(surf, cx - 14, 52 + bob, 28, 30, spec["backpack"], depth=5)
        stud(surf, cx - 8, 60 + bob, 16, 4, darken(spec["backpack"], 0.35))

    if spec.get("sword"):
        sc = spec["sword"]
        cube(surf, cx + 24, 30 + bob, 6, 44, sc, depth=3, side=1)
        cube(surf, cx + 21, 70 + bob, 12, 6, darken(sc, 0.45), depth=3)

    if glow:
        halo = make_surface(CHAR_W, CHAR_H)
        pygame.draw.ellipse(halo, with_alpha(glow, 46), (cx - 34, 26 + bob, 68, 96))
        surf.blit(halo, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    return surf


RUN_FRAMES = 8


def character_sprite(spec: dict, pose: str, frame: int, width: int, height: int) -> pygame.Surface:
    """Cached, scaled character sprite."""
    cid = spec.get("id", "unknown")
    if pose == "run":
        frame %= RUN_FRAMES
        key = f"char:{cid}:run:{frame}"
        phase = frame / RUN_FRAMES
    else:
        frame = 0
        key = f"char:{cid}:{pose}"
        phase = 0.0
    return CACHE.scaled(key, lambda: _character_frame(spec, pose, phase), width, height)


def character_portrait(spec: dict, size: int = 120) -> pygame.Surface:
    """Front-on-ish showcase sprite used by the shop/character cards."""
    key = f"portrait:{spec.get('id')}"

    def build() -> pygame.Surface:
        return _character_frame(spec, "run", 0.12)

    ratio = CHAR_H / CHAR_W
    return CACHE.scaled(key, build, size, int(size * ratio))


# --------------------------------------------------------------------------
# Coins (DOWN)
# --------------------------------------------------------------------------

COIN_FRAMES = 10
COIN_BASE = 46


def _coin_frame(frame: int) -> pygame.Surface:
    surf = make_surface(COIN_BASE, COIN_BASE)
    t = frame / COIN_FRAMES
    width = abs(math.cos(t * math.pi))
    w = max(4, int(COIN_BASE * 0.74 * width) + 4)
    h = int(COIN_BASE * 0.74)
    x = (COIN_BASE - w) // 2
    y = (COIN_BASE - h) // 2
    gold = (255, 206, 68)
    edge = (198, 138, 24)

    pygame.draw.rect(surf, edge, (x, y, w, h))
    pygame.draw.rect(surf, gold, (x + 2, y + 2, max(1, w - 4), h - 4))
    if w > 12:
        pygame.draw.rect(surf, lighten(gold, 0.45), (x + 3, y + 3, max(1, w - 6), 4))
        # A blocky "D" for DOWN.
        bx, by = x + w // 2 - 5, y + h // 2 - 8
        stud(surf, bx, by, 3, 16, edge)
        stud(surf, bx + 3, by, 6, 3, edge)
        stud(surf, bx + 3, by + 13, 6, 3, edge)
        stud(surf, bx + 8, by + 3, 3, 10, edge)
    else:
        pygame.draw.rect(surf, lighten(gold, 0.3), (x, y + 2, w, 3))
    return surf


def coin_sprite(frame: int, size: int) -> pygame.Surface:
    frame %= COIN_FRAMES
    return CACHE.scaled(f"coin:{frame}", lambda: _coin_frame(frame), size, size)


def coin_icon(size: int = 28) -> pygame.Surface:
    """Static coin used in HUD/menus next to the DOWN balance."""
    return CACHE.scaled("coin_icon", lambda: _coin_frame(0), size, size)


# --------------------------------------------------------------------------
# Power-up pickups
# --------------------------------------------------------------------------

PU_BASE = 56
POWERUP_COLORS = {
    "magnet": (255, 92, 108),
    "shield": (92, 178, 255),
    "coin_multiplier": (255, 202, 64),
    "speed_boost": (124, 240, 132),
    "super_jump": (196, 130, 255),
    "slow_motion": (120, 226, 226),
}


def _powerup_symbol(surf: pygame.Surface, kind: str, cx: int, cy: int) -> None:
    white = (255, 255, 255)
    dark = (28, 32, 48)
    if kind == "magnet":
        pygame.draw.rect(surf, white, (cx - 12, cy - 12, 8, 18))
        pygame.draw.rect(surf, white, (cx + 4, cy - 12, 8, 18))
        pygame.draw.rect(surf, white, (cx - 12, cy + 2, 24, 8))
        pygame.draw.rect(surf, dark, (cx - 12, cy - 12, 8, 6))
        pygame.draw.rect(surf, dark, (cx + 4, cy - 12, 8, 6))
    elif kind == "shield":
        pygame.draw.polygon(surf, white, [
            (cx, cy - 14), (cx + 12, cy - 8), (cx + 10, cy + 8),
            (cx, cy + 15), (cx - 10, cy + 8), (cx - 12, cy - 8)])
        pygame.draw.polygon(surf, dark, [
            (cx, cy - 9), (cx + 7, cy - 5), (cx + 6, cy + 5),
            (cx, cy + 9), (cx - 6, cy + 5), (cx - 7, cy - 5)], 2)
    elif kind == "coin_multiplier":
        pygame.draw.rect(surf, white, (cx - 13, cy - 10, 5, 5))
        pygame.draw.rect(surf, white, (cx - 8, cy - 5, 5, 5))
        pygame.draw.rect(surf, white, (cx - 3, cy, 5, 5))
        pygame.draw.rect(surf, white, (cx - 13, cy + 5, 5, 5))
        pygame.draw.rect(surf, white, (cx - 8, cy, 5, 5))
        pygame.draw.rect(surf, white, (cx - 3, cy - 5, 5, 5))
        pygame.draw.rect(surf, white, (cx + 4, cy - 10, 4, 20))
        pygame.draw.rect(surf, white, (cx + 8, cy - 10, 4, 6))
        pygame.draw.rect(surf, white, (cx + 8, cy + 4, 4, 6))
    elif kind == "speed_boost":
        for i in range(3):
            x = cx - 14 + i * 10
            pygame.draw.polygon(surf, white, [
                (x, cy - 12), (x + 9, cy), (x, cy + 12), (x + 3, cy)])
    elif kind == "super_jump":
        for i, dy in enumerate((-13, 1)):
            pygame.draw.polygon(surf, white, [
                (cx, cy + dy), (cx + 11, cy + dy + 10), (cx - 11, cy + dy + 10)])
    elif kind == "slow_motion":
        pygame.draw.rect(surf, white, (cx - 10, cy - 14, 20, 4))
        pygame.draw.rect(surf, white, (cx - 10, cy + 10, 20, 4))
        pygame.draw.polygon(surf, white, [
            (cx - 8, cy - 10), (cx + 8, cy - 10), (cx, cy)])
        pygame.draw.polygon(surf, white, [
            (cx - 8, cy + 10), (cx + 8, cy + 10), (cx, cy)])


def _powerup_frame(kind: str) -> pygame.Surface:
    surf = make_surface(PU_BASE, PU_BASE + 8)
    color = POWERUP_COLORS.get(kind, (200, 200, 200))
    cube(surf, 8, 12, 40, 40, color, depth=8)
    _powerup_symbol(surf, kind, 28, 34)
    pygame.draw.rect(surf, lighten(color, 0.5), (8, 12, 40, 40), 2)
    return surf


def powerup_sprite(kind: str, size: int) -> pygame.Surface:
    return CACHE.scaled(f"pu:{kind}", lambda: _powerup_frame(kind), size, size)


def powerup_icon(kind: str, size: int = 34) -> pygame.Surface:
    return CACHE.scaled(f"pu_icon:{kind}", lambda: _powerup_frame(kind), size, size)


# --------------------------------------------------------------------------
# Misc UI art
# --------------------------------------------------------------------------


def trophy_sprite(size: int = 96) -> pygame.Surface:
    def build() -> pygame.Surface:
        s = make_surface(96, 110)
        gold = (255, 206, 74)
        cube(s, 26, 10, 44, 34, gold, depth=8)
        cube(s, 14, 14, 12, 18, darken(gold, 0.1), depth=4, side=-1)
        cube(s, 70, 14, 12, 18, darken(gold, 0.2), depth=4)
        cube(s, 40, 44, 16, 22, darken(gold, 0.15), depth=5)
        cube(s, 26, 66, 44, 12, (198, 138, 24), depth=6)
        cube(s, 18, 78, 60, 14, (152, 104, 20), depth=6)
        stud(s, 34, 18, 28, 6, lighten(gold, 0.5))
        return s

    return CACHE.scaled("trophy", build, size, int(size * 110 / 96))


def star_sprite(size: int, filled: bool) -> pygame.Surface:
    def build() -> pygame.Surface:
        s = make_surface(32, 32)
        color = (255, 206, 74) if filled else (78, 90, 118)
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = 15 if i % 2 == 0 else 6.4
            pts.append((16 + math.cos(ang) * r, 16 + math.sin(ang) * r))
        pygame.draw.polygon(s, color, pts)
        pygame.draw.polygon(s, darken(color, 0.4), pts, 1)
        if filled:
            pygame.draw.polygon(s, lighten(color, 0.4),
                                [(16, 4), (20, 13), (12, 13)])
        return s

    return CACHE.scaled(f"star:{int(filled)}", build, size, size)


def lock_sprite(size: int = 32) -> pygame.Surface:
    def build() -> pygame.Surface:
        s = make_surface(32, 32)
        body = (188, 196, 214)
        pygame.draw.rect(s, darken(body, 0.35), (7, 14, 18, 14))
        pygame.draw.rect(s, body, (8, 15, 16, 12))
        pygame.draw.rect(s, body, (11, 5, 10, 10), 3)
        pygame.draw.rect(s, darken(body, 0.5), (15, 19, 3, 5))
        return s

    return CACHE.scaled("lock", build, size, size)


# --------------------------------------------------------------------------
# Perspective faces
#
# Obstacles and world props extend through z, so a flat scaled sprite would
# read wrong. Their geometry is projected in the modules that own it (see
# obstacles.py / world.py); this helper just fills one already-projected face
# with consistent lighting.
# --------------------------------------------------------------------------

FACE_LIGHT = {"top": 1.30, "front": 1.0, "side": 0.66, "bottom": 0.45}


def quad(
    surf: pygame.Surface,
    points: Sequence[Sequence[float]],
    color: Sequence[int],
    face: str = "front",
    outline: bool = True,
    fog: float = 0.0,
    fog_color: Sequence[int] = (150, 170, 200),
) -> None:
    """Fill one projected face, lit by which side of the block it is."""
    if len(points) < 3:
        return
    base = shade(color, FACE_LIGHT.get(face, 1.0))
    if fog > 0.0:
        base = mix(base, fog_color, min(1.0, fog))
    pts = [(int(p[0]), int(p[1])) for p in points]
    # Degenerate faces (edge-on) would raise or flicker; skip them.
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if max(xs) - min(xs) < 1 or max(ys) - min(ys) < 1:
        return
    pygame.draw.polygon(surf, base, pts)
    if outline and (max(xs) - min(xs)) > 6 and (max(ys) - min(ys)) > 6:
        pygame.draw.polygon(surf, darken(base, 0.4), pts, 1)


# --------------------------------------------------------------------------
# Roadside scenery
#
# Props sit on the verge, well off the racing line, so cheap billboards read
# perfectly well and cost a fraction of projected geometry.
#
# ``palette`` supplies three theme colours - prop_a (trunk/body),
# prop_b (foliage/secondary) and prop_c (accent/glow) - so one prop set
# re-themes across all eight worlds.
# --------------------------------------------------------------------------

SCN_W = 72
SCN_H = 120

SCENERY_KINDS = (
    "tree", "pine", "rock", "cactus", "crystal",
    "pillar", "lamp", "ruin", "mushroom", "spike", "sign",
)


def _scenery_frame(kind: str, palette: dict) -> pygame.Surface:
    s = make_surface(SCN_W, SCN_H)
    a = palette.get("prop_a", (120, 92, 56))
    b = palette.get("prop_b", (86, 158, 84))
    c = palette.get("prop_c", (255, 226, 150))
    cx = SCN_W // 2
    floor = SCN_H - 4

    if kind == "tree":
        cube(s, cx - 6, floor - 44, 12, 44, a, depth=5)
        for i, (dy, w) in enumerate(((-96, 46), (-74, 38), (-54, 28))):
            cube(s, cx - w // 2, floor + dy, w, 26, shade(b, 1.0 - i * 0.08), depth=7)
    elif kind == "pine":
        cube(s, cx - 5, floor - 30, 10, 30, a, depth=4)
        for i, (dy, w) in enumerate(((-104, 44), (-84, 34), (-64, 24), (-46, 16))):
            pygame.draw.polygon(s, shade(b, 1.0 - i * 0.07), [
                (cx, floor + dy - 14), (cx + w // 2, floor + dy + 8), (cx - w // 2, floor + dy + 8)])
    elif kind == "rock":
        cube(s, cx - 22, floor - 30, 30, 30, a, depth=9)
        cube(s, cx + 2, floor - 20, 20, 20, darken(a, 0.15), depth=7)
        cube(s, cx - 12, floor - 44, 18, 16, lighten(a, 0.1), depth=6)
    elif kind == "cactus":
        cube(s, cx - 8, floor - 72, 16, 72, b, depth=6)
        cube(s, cx - 24, floor - 54, 16, 12, b, depth=5, side=-1)
        cube(s, cx - 24, floor - 66, 12, 14, b, depth=5, side=-1)
        cube(s, cx + 8, floor - 44, 16, 12, b, depth=5)
        cube(s, cx + 20, floor - 58, 12, 16, b, depth=5)
        for dy in range(-68, -8, 12):
            stud(s, cx - 2, floor + dy, 3, 5, c)
    elif kind == "crystal":
        for dx, h, w in ((-14, 52, 16), (6, 74, 18), (22, 40, 12)):
            pygame.draw.polygon(s, b, [
                (cx + dx, floor), (cx + dx + w, floor),
                (cx + dx + w - 3, floor - h + 12), (cx + dx + w // 2, floor - h),
                (cx + dx + 3, floor - h + 12)])
            pygame.draw.polygon(s, lighten(b, 0.4), [
                (cx + dx + 3, floor - 2), (cx + dx + w // 2, floor - 2),
                (cx + dx + w // 2, floor - h + 8)])
        glow = make_surface(SCN_W, SCN_H)
        pygame.draw.ellipse(glow, with_alpha(c, 60), (cx - 24, floor - 78, 60, 84))
        s.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    elif kind == "pillar":
        for i in range(5):
            cube(s, cx - 15, floor - 22 - i * 20, 30, 20, shade(a, 1.0 - i * 0.04), depth=8)
        cube(s, cx - 20, floor - 126, 40, 12, lighten(a, 0.18), depth=9)
        stud(s, cx - 12, floor - 60, 24, 4, c)
    elif kind == "lamp":
        cube(s, cx - 4, floor - 96, 8, 96, a, depth=4)
        cube(s, cx - 14, floor - 112, 28, 18, darken(a, 0.2), depth=7)
        stud(s, cx - 10, floor - 108, 20, 11, c)
        glow = make_surface(SCN_W, SCN_H)
        pygame.draw.ellipse(glow, with_alpha(c, 74), (cx - 26, floor - 126, 52, 46))
        s.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    elif kind == "ruin":
        cube(s, cx - 26, floor - 34, 22, 34, a, depth=8)
        cube(s, cx - 4, floor - 58, 20, 58, shade(a, 0.92), depth=8)
        cube(s, cx + 16, floor - 22, 16, 22, darken(a, 0.12), depth=6)
        stud(s, cx - 2, floor - 44, 14, 4, darken(a, 0.4))
    elif kind == "mushroom":
        cube(s, cx - 7, floor - 34, 14, 34, lighten(a, 0.35), depth=5)
        pygame.draw.ellipse(s, b, (cx - 26, floor - 56, 52, 30))
        pygame.draw.ellipse(s, darken(b, 0.25), (cx - 26, floor - 44, 52, 16))
        for dx, dy in ((-14, -50), (2, -53), (12, -47)):
            pygame.draw.ellipse(s, c, (cx + dx, floor + dy, 8, 6))
    elif kind == "spike":
        pygame.draw.polygon(s, b, [
            (cx - 14, floor), (cx + 14, floor), (cx + 4, floor - 88)])
        pygame.draw.polygon(s, lighten(b, 0.35), [
            (cx - 6, floor), (cx + 2, floor), (cx + 4, floor - 84)])
    elif kind == "sign":
        cube(s, cx - 4, floor - 62, 8, 62, a, depth=4)
        cube(s, cx - 28, floor - 104, 56, 44, darken(a, 0.3), depth=8)
        for i in range(3):
            stud(s, cx - 20, floor - 96 + i * 12, 40 - i * 10, 6, c)
        glow = make_surface(SCN_W, SCN_H)
        pygame.draw.rect(glow, with_alpha(c, 52), (cx - 30, floor - 106, 60, 48))
        s.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    else:
        cube(s, cx - 12, floor - 30, 24, 30, a, depth=7)
    return s


def scenery_sprite(kind: str, theme: str, palette: dict, w: int, h: int) -> pygame.Surface:
    """Cached roadside prop. ``theme`` is the world id, so palettes never collide."""
    key = f"scn:{theme}:{kind}"
    return CACHE.scaled(key, lambda: _scenery_frame(kind, palette), w, h)


def scenery_ratio() -> float:
    return SCN_H / SCN_W


# --------------------------------------------------------------------------
# In-run effect art
# --------------------------------------------------------------------------


def shield_bubble(size: int) -> pygame.Surface:
    """Translucent dome shown around the player while a shield holds."""
    def build() -> pygame.Surface:
        d = 128
        s = make_surface(d, d)
        pygame.draw.ellipse(s, (120, 200, 255, 40), (0, 0, d, d))
        pygame.draw.ellipse(s, (170, 226, 255, 130), (0, 0, d, d), 4)
        pygame.draw.ellipse(s, (255, 255, 255, 70), (int(d * 0.22), int(d * 0.14),
                                                     int(d * 0.3), int(d * 0.18)))
        return s

    return CACHE.scaled("shield_bubble", build, size, size)


def combo_badge(tier: int, size: int = 56) -> pygame.Surface:
    """Chevron badge whose colour warms as the combo tier climbs."""
    tier = max(1, int(tier))

    def build() -> pygame.Surface:
        s = make_surface(64, 64)
        hot = min(1.0, (tier - 1) / 7.0)
        color = mix((86, 204, 255), (255, 96, 148), hot)
        pygame.draw.polygon(s, color, [(32, 4), (60, 32), (32, 60), (4, 32)])
        pygame.draw.polygon(s, lighten(color, 0.45), [(32, 4), (60, 32), (32, 60), (4, 32)], 3)
        for i in range(min(3, tier)):
            y = 20 + i * 10
            pygame.draw.polygon(s, (255, 255, 255), [
                (32, y), (42, y + 7), (38, y + 7), (32, y + 4), (26, y + 7), (22, y + 7)])
        return s

    return CACHE.scaled(f"combo:{tier}", build, size, size)


def finish_gate(w: int, h: int) -> pygame.Surface:
    """The banner that marks the end of a level."""
    def build() -> pygame.Surface:
        s = make_surface(240, 150)
        post = (206, 214, 232)
        cube(s, 8, 24, 22, 126, post, depth=8)
        cube(s, 210, 24, 22, 126, post, depth=8)
        cube(s, 8, 8, 224, 30, (86, 204, 255), depth=9)
        for i in range(11):
            if i % 2 == 0:
                stud(s, 14 + i * 20, 14, 20, 18, (255, 255, 255))
        stud(s, 8, 38, 224, 4, (36, 132, 190))
        return s

    return CACHE.scaled("finish_gate", build, w, h)


def speed_streak(w: int, h: int) -> pygame.Surface:
    """Soft white streak used for the speed-boost effect."""
    def build() -> pygame.Surface:
        s = make_surface(64, 8)
        for i in range(64):
            a = int(160 * (i / 64.0) ** 2)
            pygame.draw.line(s, (255, 255, 255, a), (i, 3), (i, 5))
        return s

    return CACHE.scaled("streak", build, w, h)
