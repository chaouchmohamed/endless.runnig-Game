"""
camera.py - The one and only pseudo-3D projection.

``settings.py`` documents the maths; this module is the single implementation so
the road, obstacles, coins and particles can never disagree about where a world
point lands on screen.

    world space: x = lateral (0 = middle lane)
                 y = up      (0 = road surface)
                 z = depth   (0 = the player, grows into the screen)

Nothing here holds state, so every function is safe to call from anywhere.
"""

from __future__ import annotations

from typing import Tuple

from settings import (
    BASE_DRAW_Z,
    CAM_HEIGHT,
    CAM_Z,
    CX,
    DRAW_Z_PER_SPEED,
    FOCAL,
    HORIZON_Y,
    MAX_DRAW_Z,
    NEAR_Z,
)

# Never divide by (almost) zero, however odd the incoming z is.
_MIN_DENOM = 1.0


def scale_at(z: float) -> float:
    """Perspective scale factor for depth ``z``. 1.73 at the player, ~0 far away."""
    return FOCAL / max(_MIN_DENOM, z + CAM_Z)


def project(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """World point -> (screen_x, screen_y, scale)."""
    s = scale_at(z)
    return CX + x * s, HORIZON_Y + (CAM_HEIGHT - y) * s, s


def ground_y(z: float) -> float:
    """Screen y of the road surface at depth ``z``."""
    return HORIZON_Y + CAM_HEIGHT * scale_at(z)


def screen_x(x: float, z: float) -> float:
    return CX + x * scale_at(z)


def visible(z: float) -> bool:
    """False once something has passed behind the camera."""
    return z > NEAR_Z


def draw_z(speed: float) -> float:
    """How far ahead to draw. Faster running -> see further."""
    return min(MAX_DRAW_Z, BASE_DRAW_Z + max(0.0, speed) * DRAW_Z_PER_SPEED)


def fog_amount(z: float, far: float) -> float:
    """0 near the player, 1 at the draw distance - used to haze distant geometry."""
    if far <= 0.0:
        return 0.0
    t = z / far
    if t <= 0.55:
        return 0.0
    return min(1.0, (t - 0.55) / 0.45)
