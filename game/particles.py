"""
particles.py - Screen-space effects and camera shake.

Effects are cosmetic and short-lived, so they live in screen space: no
projection, no world bookkeeping, just a pooled list that decays. Both systems
read the player's ``particles`` / ``screen_shake`` preferences and become
no-ops when they are off, which is also what makes them cheap to disable on a
slow machine.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence, Tuple

import pygame

import voxel
from settings import HEIGHT, UI_GOLD, WIDTH

MAX_PARTICLES = 420


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "full", "size", "color", "gravity", "fade")

    def __init__(self, x: float, y: float, vx: float, vy: float, life: float,
                 size: float, color: Sequence[int], gravity: float = 900.0,
                 fade: bool = True) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.full = life
        self.size = size
        self.color = (int(color[0]), int(color[1]), int(color[2]))
        self.gravity = gravity
        self.fade = fade


class ParticleSystem:
    """A single pooled list of blocky particles."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.items: List[Particle] = []
        self.rng = random.Random(20250826)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.items.clear()

    def clear(self) -> None:
        self.items.clear()

    # ------------------------------------------------------------- emitters
    def _add(self, particle: Particle) -> None:
        if len(self.items) >= MAX_PARTICLES:
            # Drop the oldest rather than refusing the newest - the newest is
            # the one the player just caused and expects to see.
            del self.items[0]
        self.items.append(particle)

    def coin_sparkle(self, x: float, y: float, count: int = 7) -> None:
        if not self.enabled:
            return
        for _ in range(count):
            ang = self.rng.uniform(0.0, math.tau)
            spd = self.rng.uniform(70.0, 210.0)
            self._add(Particle(
                x, y, math.cos(ang) * spd, math.sin(ang) * spd - 60.0,
                self.rng.uniform(0.28, 0.5), self.rng.uniform(2.0, 5.0),
                voxel.lighten(UI_GOLD, self.rng.uniform(0.0, 0.5)), gravity=620.0))

    def dust(self, x: float, y: float, color: Sequence[int] = (196, 190, 176),
             count: int = 10) -> None:
        if not self.enabled:
            return
        for _ in range(count):
            self._add(Particle(
                x + self.rng.uniform(-24.0, 24.0), y,
                self.rng.uniform(-140.0, 140.0), self.rng.uniform(-150.0, -40.0),
                self.rng.uniform(0.24, 0.46), self.rng.uniform(2.0, 6.0),
                color, gravity=520.0))

    def hit_burst(self, x: float, y: float, color: Sequence[int] = (255, 96, 96)) -> None:
        if not self.enabled:
            return
        for _ in range(22):
            ang = self.rng.uniform(0.0, math.tau)
            spd = self.rng.uniform(120.0, 420.0)
            self._add(Particle(
                x, y, math.cos(ang) * spd, math.sin(ang) * spd,
                self.rng.uniform(0.35, 0.7), self.rng.uniform(3.0, 7.0),
                voxel.lighten(color, self.rng.uniform(0.0, 0.4)), gravity=760.0))

    def ring(self, x: float, y: float, color: Sequence[int], count: int = 16) -> None:
        """An outward puff used when a power-up is picked up."""
        if not self.enabled:
            return
        for i in range(count):
            ang = math.tau * i / count
            spd = self.rng.uniform(180.0, 260.0)
            self._add(Particle(
                x, y, math.cos(ang) * spd, math.sin(ang) * spd * 0.6,
                0.42, 4.0, color, gravity=90.0))

    def speed_lines(self, count: int = 3) -> None:
        """Streaks down the edges of the screen while boosted."""
        if not self.enabled:
            return
        for _ in range(count):
            side = self.rng.choice((-1, 1))
            x = WIDTH * 0.5 + side * self.rng.uniform(WIDTH * 0.28, WIDTH * 0.5)
            y = self.rng.uniform(HEIGHT * 0.25, HEIGHT)
            self._add(Particle(
                x, y, side * 240.0, 720.0, 0.24, self.rng.uniform(2.0, 4.0),
                (255, 255, 255), gravity=0.0))

    def star_pop(self, x: float, y: float) -> None:
        if not self.enabled:
            return
        for _ in range(26):
            ang = self.rng.uniform(-math.pi, 0.0)
            spd = self.rng.uniform(160.0, 460.0)
            self._add(Particle(
                x, y, math.cos(ang) * spd, math.sin(ang) * spd,
                self.rng.uniform(0.5, 1.0), self.rng.uniform(3.0, 6.0),
                voxel.lighten(UI_GOLD, self.rng.uniform(0.0, 0.6)), gravity=700.0))

    # ---------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        if not self.items:
            return
        alive: List[Particle] = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0.0:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            if -40.0 < p.x < WIDTH + 40.0 and p.y < HEIGHT + 60.0:
                alive.append(p)
        self.items = alive

    def draw(self, surf: pygame.Surface) -> None:
        for p in self.items:
            t = p.life / p.full if p.full > 0.0 else 0.0
            size = max(1, int(p.size * (0.4 + 0.6 * t)))
            if p.fade and t < 0.55:
                # Cheap fade: shrink and darken rather than per-particle alpha.
                color = voxel.mix((26, 30, 42), p.color, max(0.15, t / 0.55))
            else:
                color = p.color
            pygame.draw.rect(surf, color, (int(p.x), int(p.y), size, size))


class ScreenShake:
    """Decaying shake, sampled as a damped oscillation so it reads smoothly."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.amount = 0.0
        self.time = 0.0
        self.rng = random.Random(4242)
        self._phase = 0.0

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.amount = 0.0

    def kick(self, amount: float) -> None:
        if not self.enabled:
            return
        self.amount = min(34.0, max(self.amount, amount))
        self._phase = self.rng.uniform(0.0, math.tau)

    def update(self, dt: float) -> None:
        self.time += dt
        if self.amount > 0.0:
            self.amount = max(0.0, self.amount - self.amount * 7.0 * dt - 6.0 * dt)

    def offset(self) -> Tuple[float, float]:
        if not self.enabled or self.amount <= 0.05:
            return 0.0, 0.0
        t = self.time * 42.0 + self._phase
        return (math.sin(t) * self.amount,
                math.cos(t * 1.37) * self.amount * 0.7)

    def clear(self) -> None:
        self.amount = 0.0
