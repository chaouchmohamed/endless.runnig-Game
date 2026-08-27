"""
obstacles.py - The eight hazards, drawn as real boxes in world space.

The central idea: every obstacle is a genuine 3D box, and collision is one AABB
test against ``Player.hitbox()``. The *shape* encodes the required action, so
there is no table of special cases -

  * a low box cannot be run through but can be jumped          -> jump
  * a box floating at head height clears the sliding hitbox    -> slide
  * a full-height box clears nothing                           -> change lane

Only the pit needs a rule of its own, because it is the absence of road.

Obstacles keep their absolute world depth (``wz``) and derive screen depth as
``wz - travelled`` every frame. Nothing is integrated per-frame, so positions
cannot drift over a long run.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

import camera
import voxel
from settings import (
    CAM_HEIGHT,
    LANE_W,
    LANE_X,
    NEAR_Z,
    WIDTH,
)

# --------------------------------------------------------------------------
# Kind table
#
# ``action`` is what the player must do, and is what level.py's generator reads
# when it guarantees a level is solvable.
#   w/h/d  - size in world units
#   y      - height of the box's underside above the road
#   lanes  - how many lanes the box covers
# --------------------------------------------------------------------------

KINDS: Dict[str, dict] = {
    # Jump over it. Peak jump height is ~97 units, so 62 leaves a wide window.
    "barrier":  {"action": "jump",  "w": 110.0, "h": 62.0,  "d": 48.0,  "y": 0.0,   "lanes": 1},
    # Slide under it. Standing hitbox is 112 tall, sliding is 49 - so 60 is the
    # gap that admits exactly one of them.
    "bar":      {"action": "slide", "w": 110.0, "h": 90.0,  "d": 40.0,  "y": 60.0,  "lanes": 1},
    "wide_bar": {"action": "slide", "w": 272.0, "h": 90.0,  "d": 44.0,  "y": 60.0,  "lanes": 2},
    # Nothing clears these.
    "block":    {"action": "dodge", "w": 110.0, "h": 175.0, "d": 64.0,  "y": 0.0,   "lanes": 1},
    "train":    {"action": "dodge", "w": 112.0, "h": 185.0, "d": 520.0, "y": 0.0,   "lanes": 1},
    "mover":    {"action": "dodge", "w": 104.0, "h": 170.0, "d": 60.0,  "y": 0.0,   "lanes": 1},
    "crusher":  {"action": "dodge", "w": 110.0, "h": 120.0, "d": 56.0,  "y": 0.0,   "lanes": 1},
    # A gap in the road. Modelled as a very low box so the same AABB test works.
    "pit":      {"action": "jump",  "w": 126.0, "h": 8.0,   "d": 170.0, "y": -2.0,  "lanes": 1},
}

ALL_KINDS = tuple(KINDS.keys())
CRUSHER_LIFT = 132.0          # how high a crusher rises at the top of its cycle
CRUSHER_PERIOD = 1.7          # seconds for a full up/down cycle
MOVER_PERIOD = 2.4            # seconds for a full lane sweep


def action_of(kind: str) -> str:
    return KINDS.get(kind, KINDS["block"])["action"]


# --------------------------------------------------------------------------
# One obstacle
# --------------------------------------------------------------------------


class Obstacle:
    """A single hazard at an absolute world depth."""

    __slots__ = ("kind", "spec", "lane", "wz", "phase", "counted", "hit", "x", "y0")

    def __init__(self, kind: str, lane: int, wz: float, phase: float = 0.0) -> None:
        self.kind = kind
        self.spec = KINDS.get(kind, KINDS["block"])
        self.lane = max(0, min(2, int(lane)))
        self.wz = float(wz)
        self.phase = phase
        self.counted = False
        self.hit = False

        if self.spec["lanes"] == 2:
            # Anchored so it covers this lane and the next one along.
            lane_b = self.lane + 1 if self.lane < 2 else self.lane - 1
            self.x = (LANE_X[self.lane] + LANE_X[lane_b]) * 0.5
        else:
            self.x = LANE_X[self.lane]
        self.y0 = self.spec["y"]

    # ------------------------------------------------------------- animation
    def animate(self, elapsed: float) -> None:
        """Movers sweep sideways; crushers rise and fall."""
        if self.kind == "mover":
            t = (elapsed / MOVER_PERIOD + self.phase) * math.tau
            # Sweep across one lane either side of its home lane, clamped to the road.
            home = LANE_X[self.lane]
            reach = LANE_W
            if self.lane == 0:
                home, reach = LANE_X[0] + LANE_W * 0.5, LANE_W * 0.5
            elif self.lane == 2:
                home, reach = LANE_X[2] - LANE_W * 0.5, LANE_W * 0.5
            self.x = home + math.sin(t) * reach
        elif self.kind == "crusher":
            t = (elapsed / CRUSHER_PERIOD + self.phase) * math.tau
            self.y0 = CRUSHER_LIFT * (0.5 + 0.5 * math.cos(t))

    # -------------------------------------------------------------- geometry
    def z(self, travelled: float) -> float:
        return self.wz - travelled

    def box(self, travelled: float) -> Tuple[float, float, float, float, float, float]:
        s = self.spec
        hw = s["w"] * 0.5
        z0 = self.z(travelled)
        return (
            self.x - hw, self.x + hw,
            self.y0, self.y0 + s["h"],
            z0 - s["d"] * 0.5, z0 + s["d"] * 0.5,
        )

    def hits(self, player_box: Sequence[float], travelled: float) -> bool:
        ax0, ax1, ay0, ay1, az0, az1 = self.box(travelled)
        bx0, bx1, by0, by1, bz0, bz1 = player_box
        return (ax0 < bx1 and bx0 < ax1
                and ay0 < by1 and by0 < ay1
                and az0 < bz1 and bz0 < az1)

    # ------------------------------------------------------------------ draw
    def draw(self, surf: pygame.Surface, travelled: float, palette: dict,
             far: float, haze: Sequence[int], shake: Tuple[float, float]) -> None:
        z_mid = self.z(travelled)
        if z_mid <= NEAR_Z or z_mid > far:
            return
        if self.kind == "pit":
            self._draw_pit(surf, travelled, palette, far, haze, shake)
            return

        x0, x1, y0, y1, z0, z1 = self.box(travelled)
        z0 = max(z0, NEAR_Z + 1.0)
        if z1 <= z0:
            return

        sx, sy = shake
        fog = camera.fog_amount(z_mid, far)
        color = palette.get("main", (170, 90, 70))
        accent = palette.get("accent", (250, 226, 150))
        metal = palette.get("metal", (180, 190, 206))
        if self.kind in ("bar", "wide_bar"):
            color = metal
        elif self.kind == "mover":
            color = accent
        elif self.kind == "crusher":
            color = metal

        def pt(x: float, y: float, z: float) -> Tuple[float, float]:
            px, py, _ = camera.project(x, y, z)
            return px + sx, py + sy

        # Top face (the camera eye sits at CAM_HEIGHT, so we look down on
        # anything shorter than that and up at anything taller).
        if y1 < CAM_HEIGHT:
            voxel.quad(surf, [pt(x0, y1, z1), pt(x1, y1, z1),
                              pt(x1, y1, z0), pt(x0, y1, z0)],
                       color, face="top", fog=fog, fog_color=haze)
        elif y0 > CAM_HEIGHT:
            voxel.quad(surf, [pt(x0, y0, z1), pt(x1, y0, z1),
                              pt(x1, y0, z0), pt(x0, y0, z0)],
                       color, face="bottom", fog=fog, fog_color=haze)

        # Whichever side face is turned toward the camera.
        cx = (x0 + x1) * 0.5
        if cx > 0.0:
            voxel.quad(surf, [pt(x0, y1, z1), pt(x0, y1, z0),
                              pt(x0, y0, z0), pt(x0, y0, z1)],
                       color, face="side", fog=fog, fog_color=haze)
        elif cx < 0.0:
            voxel.quad(surf, [pt(x1, y1, z1), pt(x1, y1, z0),
                              pt(x1, y0, z0), pt(x1, y0, z1)],
                       color, face="side", fog=fog, fog_color=haze)

        # Front face last - it is nearest the camera.
        front = [pt(x0, y1, z0), pt(x1, y1, z0), pt(x1, y0, z0), pt(x0, y0, z0)]
        voxel.quad(surf, front, color, face="front", fog=fog, fog_color=haze)
        self._draw_detail(surf, front, accent, fog, haze)

        # Crushers hang from a shaft so the danger is readable before it drops.
        if self.kind == "crusher" and self.y0 > 2.0:
            top = [pt(x0 + 18, y0 + self.spec["h"] + 260, z0), pt(x1 - 18, y0 + self.spec["h"] + 260, z0),
                   pt(x1 - 18, y1, z0), pt(x0 + 18, y1, z0)]
            voxel.quad(surf, top, voxel.darken(metal, 0.4), face="front",
                       outline=False, fog=fog, fog_color=haze)

    def _draw_detail(self, surf: pygame.Surface, front: List[Tuple[float, float]],
                     accent: Sequence[int], fog: float, haze: Sequence[int]) -> None:
        """Hazard stripes / markings on the front face, when it is big enough."""
        (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = front
        w = trx - tlx
        h = bry - try_
        if w < 16 or h < 10:
            return
        color = voxel.mix(accent, haze, min(1.0, fog))
        if self.kind in ("barrier", "block", "train"):
            bands = 3 if h > 40 else 1
            for i in range(bands):
                t0 = 0.18 + i * 0.28
                y = try_ + h * t0
                pygame.draw.rect(surf, color, (int(tlx + w * 0.12), int(y),
                                               max(2, int(w * 0.76)), max(2, int(h * 0.09))))
        elif self.kind in ("bar", "wide_bar"):
            step = max(10, int(w / 8))
            for x in range(int(tlx) + 4, int(trx) - 4, step):
                pygame.draw.rect(surf, color, (x, int(try_ + h * 0.3),
                                               max(2, step // 2), max(2, int(h * 0.4))))
        elif self.kind == "mover":
            pygame.draw.polygon(surf, color, [
                (tlx + w * 0.5, try_ + h * 0.3), (tlx + w * 0.78, try_ + h * 0.55),
                (tlx + w * 0.5, try_ + h * 0.8), (tlx + w * 0.22, try_ + h * 0.55)])
        elif self.kind == "crusher":
            for i in range(4):
                x = tlx + w * (0.14 + i * 0.24)
                pygame.draw.polygon(surf, color, [
                    (x, bry), (x + w * 0.12, bry), (x + w * 0.06, bry - h * 0.3)])

    def _draw_pit(self, surf: pygame.Surface, travelled: float, palette: dict,
                  far: float, haze: Sequence[int], shake: Tuple[float, float]) -> None:
        s = self.spec
        hw = s["w"] * 0.5
        zc = self.z(travelled)
        z0 = max(zc - s["d"] * 0.5, NEAR_Z + 1.0)
        z1 = zc + s["d"] * 0.5
        if z1 <= z0:
            return
        sx, sy = shake
        fog = camera.fog_amount(zc, far)

        def pt(x: float, z: float) -> Tuple[float, float]:
            return camera.screen_x(x, z) + sx, camera.ground_y(z) + sy

        hole = (16, 18, 26)
        voxel.quad(surf, [pt(self.x - hw, z1), pt(self.x + hw, z1),
                          pt(self.x + hw, z0), pt(self.x - hw, z0)],
                   hole, face="front", outline=False, fog=fog * 0.5, fog_color=haze)
        # A lip on the near edge so the gap reads as depth, not a painted patch.
        lip = palette.get("accent", (250, 226, 150))
        pygame.draw.line(surf, voxel.mix(lip, haze, fog),
                         pt(self.x - hw, z0), pt(self.x + hw, z0), 3)


# --------------------------------------------------------------------------
# The field of obstacles for one run
# --------------------------------------------------------------------------


class ObstacleField:
    """Streams a level's pre-generated rows into live obstacles.

    Rows come from ``level.LevelPlan`` as ``(world_z, [(lane, kind), ...])`` and
    are already guaranteed solvable, so this class only has to spawn, animate,
    collide and retire them.
    """

    LOOKAHEAD = 300.0             # spawn this far beyond the draw distance

    def __init__(self, rows: Sequence[Tuple[float, Sequence[Tuple[int, str]]]],
                 palette: dict, haze: Sequence[int] = (150, 170, 200)) -> None:
        self.rows = list(rows)
        self.palette = palette
        self.haze = haze
        self.active: List[Obstacle] = []
        self._next = 0
        self.dodged = 0
        self._travelled = 0.0

    def reset(self) -> None:
        self.active.clear()
        self._next = 0
        self.dodged = 0
        self._travelled = 0.0

    # ---------------------------------------------------------------- update
    def update(self, dt: float, speed: float, travelled: float, elapsed: float) -> int:
        """Spawn, animate and retire. Returns how many rows were cleared."""
        far = camera.draw_z(speed)
        limit = travelled + far + self.LOOKAHEAD
        while self._next < len(self.rows) and self.rows[self._next][0] <= limit:
            wz, items = self.rows[self._next]
            for i, (lane, kind) in enumerate(items):
                self.active.append(Obstacle(kind, lane, wz, phase=(i * 0.37 + wz * 0.0013) % 1.0))
            self._next += 1

        cleared = 0
        still: List[Obstacle] = []
        for obs in self.active:
            obs.animate(elapsed)
            if obs.z(travelled) < NEAR_Z:
                if not obs.hit:
                    cleared += 1
                continue
            still.append(obs)
        self.active = still
        self.dodged += cleared
        return cleared

    def collide(self, player) -> Optional[Obstacle]:
        """First obstacle overlapping the player, or None.

        ``set_travelled`` must have been called for this frame first.
        """
        box = player.hitbox()
        travelled = self._travelled
        for obs in self.active:
            if obs.hit:
                continue
            # Cheap depth reject before the full test.
            if abs(obs.z(travelled)) > 400.0:
                continue
            if obs.hits(box, travelled):
                return obs
        return None

    def set_travelled(self, travelled: float) -> None:
        self._travelled = travelled

    def remaining(self) -> int:
        return len(self.rows) - self._next

    # ------------------------------------------------------------------ draw
    def draw(self, surf: pygame.Surface, travelled: float, speed: float,
             shake: Tuple[float, float] = (0.0, 0.0),
             passed: Optional[bool] = None) -> None:
        """Draw the field, far to near.

        ``passed`` splits the field around the player, who sits at z = 0:
        False draws only what is still ahead, True only what has gone by (and so
        is nearer the camera than the player sprite), None draws everything.
        """
        far = camera.draw_z(speed)
        for obs in sorted(self.active, key=lambda o: -o.wz):
            if passed is not None:
                is_passed = obs.z(travelled) < 0.0
                if is_passed != passed:
                    continue
            obs.draw(surf, travelled, self.palette, far, self.haze, shake)
