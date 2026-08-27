"""
collectibles.py - DOWN coins and power-up pickups.

Both stream out of the level plan the same way obstacles do: absolute world
depth, derived screen depth. The one wrinkle is the magnet, which mutates a
coin's world position so it flies to the player - once pulled, a coin keeps its
new course.

Nothing here touches the save file. Coins are reported upward and credited
through ``currency.Wallet``, so the balance and the save can never disagree.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import pygame

import camera
import voxel
from settings import (
    COIN_VALUE,
    LANE_X,
    MAGNET_RANGE,
    NEAR_Z,
    PLAYER_H,
    WIDTH,
)

COIN_SIZE = 42.0          # world units across
PU_SIZE = 64.0
COLLECT_MARGIN = 30.0     # generosity added to the player hitbox when collecting
MAGNET_SPEED = 1250.0     # world units per second of pull


class Coin:
    __slots__ = ("x", "y", "wz", "taken", "pulled", "spin")

    def __init__(self, wz: float, lane: int, y: float) -> None:
        self.x = LANE_X[max(0, min(2, int(lane)))]
        self.y = float(y)
        self.wz = float(wz)
        self.taken = False
        self.pulled = False
        self.spin = (wz * 0.021) % 1.0


class Pickup:
    __slots__ = ("kind", "x", "y", "wz", "taken", "bob")

    def __init__(self, wz: float, lane: int, kind: str) -> None:
        self.kind = kind
        self.x = LANE_X[max(0, min(2, int(lane)))]
        self.y = 54.0
        self.wz = float(wz)
        self.taken = False
        self.bob = (wz * 0.017) % 1.0


class CollectibleField:
    """Streams a level's coins and pickups, and handles collection."""

    LOOKAHEAD = 300.0

    def __init__(self, coins: Sequence[Tuple[float, int, float]],
                 powerups: Sequence[Tuple[float, int, str]]) -> None:
        self._coin_src = list(coins)
        self._pu_src = list(powerups)
        self.coins: List[Coin] = []
        self.pickups: List[Pickup] = []
        self._next_coin = 0
        self._next_pu = 0
        self.collected = 0

    def reset(self) -> None:
        self.coins.clear()
        self.pickups.clear()
        self._next_coin = 0
        self._next_pu = 0
        self.collected = 0

    def remaining_coins(self) -> int:
        return len(self._coin_src) - self._next_coin + len(self.coins)

    # ---------------------------------------------------------------- update
    def update(self, dt: float, speed: float, travelled: float, player,
               magnet_range: float = 0.0) -> Tuple[int, List[str]]:
        """Spawn, magnetise, collect, retire.

        Returns ``(coins_collected, [powerup_kind, ...])`` for this frame.
        """
        far = camera.draw_z(speed)
        limit = travelled + far + self.LOOKAHEAD

        while self._next_coin < len(self._coin_src) and self._coin_src[self._next_coin][0] <= limit:
            wz, lane, y = self._coin_src[self._next_coin]
            self.coins.append(Coin(wz, lane, y))
            self._next_coin += 1
        while self._next_pu < len(self._pu_src) and self._pu_src[self._next_pu][0] <= limit:
            wz, lane, kind = self._pu_src[self._next_pu]
            self.pickups.append(Pickup(wz, lane, kind))
            self._next_pu += 1

        px0, px1, py0, py1, pz0, pz1 = player.hitbox()
        m = COLLECT_MARGIN
        aim_y = player.y + PLAYER_H * 0.45

        gained = 0
        live_coins: List[Coin] = []
        for coin in self.coins:
            dz = coin.wz - travelled
            if dz < NEAR_Z - 100.0:
                continue

            if magnet_range > 0.0:
                dx = player.x - coin.x
                dy = aim_y - coin.y
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist < magnet_range and dist > 1.0:
                    coin.pulled = True
                if coin.pulled:
                    step = MAGNET_SPEED * dt / max(1.0, dist)
                    step = min(1.0, step)
                    coin.x += dx * step
                    coin.y += dy * step
                    coin.wz -= dz * step
                    dz = coin.wz - travelled

            if (px0 - m < coin.x < px1 + m
                    and py0 - m < coin.y < py1 + m
                    and pz0 - m < dz < pz1 + m):
                gained += COIN_VALUE
                self.collected += 1
                continue
            live_coins.append(coin)
        self.coins = live_coins

        taken: List[str] = []
        live_pu: List[Pickup] = []
        for pu in self.pickups:
            dz = pu.wz - travelled
            if dz < NEAR_Z - 100.0:
                continue
            if (px0 - m < pu.x < px1 + m
                    and py0 - m * 2 < pu.y < py1 + m * 2
                    and pz0 - m < dz < pz1 + m):
                taken.append(pu.kind)
                continue
            live_pu.append(pu)
        self.pickups = live_pu

        return gained, taken

    # ------------------------------------------------------------------ draw
    def draw(self, surf: pygame.Surface, travelled: float, speed: float,
             elapsed: float, shake: Tuple[float, float] = (0.0, 0.0)) -> None:
        far = camera.draw_z(speed)
        sx, sy = shake

        for coin in sorted(self.coins, key=lambda c: -c.wz):
            z = coin.wz - travelled
            if z <= NEAR_Z or z > far:
                continue
            scale = camera.scale_at(z)
            size = int(COIN_SIZE * scale)
            if size < 4:
                continue
            px, py, _ = camera.project(coin.x, coin.y, z)
            px += sx
            py += sy
            if px < -size or px > WIDTH + size:
                continue
            frame = int((elapsed * 9.0 + coin.spin * voxel.COIN_FRAMES)) % voxel.COIN_FRAMES
            surf.blit(voxel.coin_sprite(frame, size), (px - size / 2, py - size / 2))

        for pu in sorted(self.pickups, key=lambda p: -p.wz):
            z = pu.wz - travelled
            if z <= NEAR_Z or z > far:
                continue
            scale = camera.scale_at(z)
            size = int(PU_SIZE * scale)
            if size < 6:
                continue
            bob = math.sin((elapsed * 2.4 + pu.bob) * math.tau) * 12.0
            px, py, _ = camera.project(pu.x, pu.y + bob, z)
            px += sx
            py += sy
            if px < -size or px > WIDTH + size:
                continue
            glow = int(size * 1.5)
            halo = voxel.CACHE.scaled(
                f"pu_halo:{pu.kind}",
                lambda k=pu.kind: _halo(k),
                glow, glow,
            )
            surf.blit(halo, (px - glow / 2, py - glow / 2), special_flags=pygame.BLEND_RGBA_ADD)
            surf.blit(voxel.powerup_sprite(pu.kind, size), (px - size / 2, py - size / 2))


def _halo(kind: str) -> pygame.Surface:
    color = voxel.POWERUP_COLORS.get(kind, (200, 200, 200))
    s = voxel.make_surface(96, 96)
    for r, a in ((46, 24), (34, 30), (22, 38)):
        pygame.draw.circle(s, voxel.with_alpha(color, a), (48, 48), r)
    return s
