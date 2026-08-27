"""
run.py - One live run: the only place gameplay rules are applied.

Holds the player, the level plan, the obstacle field, the collectibles, the
power-up timers and the score. ``main.py`` drives it with ``update(dt)`` and
draws it, and gets back a single string when the run ends - so the state machine
never has to know how any of this works.

Scoring is split deliberately: distance accrues passively and is never combo'd,
while coins, power-ups and dodges are banked *at the moment they are earned* and
multiplied by the combo tier that was live at that instant. That way a combo
rewards the risk that built it rather than retroactively inflating the whole run.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame

import camera
import collectibles
import level as level_mod
import obstacles
import particles as particles_mod
import voxel
import world as world_mod
from player import Player, character_bonus
from powerups import PowerupManager
from settings import (
    COMBO_MAX_TIER,
    COMBO_STEP,
    COMBO_TIMEOUT,
    HEIGHT,
    INVULN_AFTER_HIT,
    METER,
    NEAR_Z,
    PLAYER_H,
    SCORE_PER_COIN,
    SCORE_PER_DODGE,
    SCORE_PER_METER,
    SCORE_PER_POWERUP,
    SPEED_RAMP,
    WIDTH,
)

COMBO_TIER_STEP = 0.25            # each tier above 1 adds 25% to earned points
DEATH_TIME = 1.15                 # death animation before the game-over screen
FINISH_GATE_H = 300.0             # world units tall


class RunSession:
    """A single attempt at a single level."""

    def __init__(self, save, wallet, audio, particle_system, shake) -> None:
        self.save = save
        self.wallet = wallet
        self.audio = audio
        self.particles = particle_system
        self.shake = shake

        self.player = Player(save.data.get("character", "starter"))
        self.powerups = PowerupManager(save, self.player.character_id)
        self.plan: Optional[level_mod.LevelPlan] = None
        self.level = 1
        self.world_spec: dict = world_mod.WORLDS[0]
        self.renderer: Optional[world_mod.WorldRenderer] = None
        self.field: Optional[obstacles.ObstacleField] = None
        self.items: Optional[collectibles.CollectibleField] = None
        self._sfx = (lambda name: self.audio.play(name)) if audio else None
        self.started = False

    # ------------------------------------------------------------------ setup
    def start(self, level_number: int) -> None:
        """Build a fresh run for ``level_number``."""
        self.plan = level_mod.get_plan(level_number)
        self.level = self.plan.level
        self.world_spec = world_mod.resolve_world(self.save, self.plan.level)

        character = self.save.data.get("character", "starter")
        self.player.set_character(character)
        self.player.reset()
        self.powerups.reset(character)

        self.renderer = world_mod.WorldRenderer(self.world_spec, seed=self.plan.level * 31 + 7)
        self.field = obstacles.ObstacleField(
            self.plan.rows, self.world_spec["obstacle"], self.world_spec["haze"])
        self.items = collectibles.CollectibleField(self.plan.coins, self.plan.powerups)

        self.travelled = 0.0
        self.elapsed = 0.0
        self.base_speed = self.plan.start_speed
        self.speed = self.base_speed

        self.coins = 0
        self.down_earned = 0
        self.dodges = 0
        self.pu_taken = 0
        self.earned_score = 0.0
        self.combo_tier = 1
        self.combo_count = 0
        self.combo_timer = 0.0
        self.best_tier = 1

        self.dying = 0.0
        self.dead = False
        self.finished = False
        self.started = True

        self.score_mult = 1.0 + float(character_bonus(character, "score_mult", 0.0))
        self.coin_bonus = 1.0 + float(character_bonus(character, "coin_mult", 0.0))

        self.particles.clear()
        self.shake.clear()

    # ------------------------------------------------------------------ input
    def handle_action(self, action: str) -> None:
        if not self.started or self.dying > 0.0 or self.finished:
            return
        if action == "left":
            self.player.move_left()
            if self.audio:
                self.audio.play("move", 0.7)
        elif action == "right":
            self.player.move_right()
            if self.audio:
                self.audio.play("move", 0.7)
        elif action == "jump":
            if self.player.jump() and self.audio:
                self.audio.play("jump")
        elif action == "slide":
            if self.player.slide() and self.audio:
                self.audio.play("slide", 0.8)

    # ----------------------------------------------------------------- update
    def update(self, dt: float) -> Optional[str]:
        """Advance the run. Returns 'died', 'completed', or None."""
        if not self.started or self.plan is None:
            return None
        self.elapsed += dt

        if self.dying > 0.0:
            return self._update_dying(dt)

        # --- speed: ramp toward the level cap, then apply power-ups ---------
        self.base_speed += (self.plan.cap_speed - self.base_speed) * SPEED_RAMP * dt
        self.speed = self.base_speed * self.powerups.speed_mult()

        was_airborne = not self.player.on_ground
        self.travelled += self.speed * dt

        # --- systems --------------------------------------------------------
        expired = self.powerups.update(dt)
        self.player.super_jump = self.powerups.super_jump()
        self.player.update(dt, self.speed, self._sfx)

        if was_airborne and self.player.on_ground:
            self._on_land()

        self.renderer.update(dt, self.speed, self.travelled)
        self.field.set_travelled(self.travelled)
        cleared = self.field.update(dt, self.speed, self.travelled, self.elapsed)
        if cleared:
            self._on_dodge(cleared)

        gained, taken = self.items.update(
            dt, self.speed, self.travelled, self.player, self.powerups.magnet_range())
        if gained:
            self._on_coins(gained)
        for kind in taken:
            self._on_powerup(kind)

        # --- combo decay ----------------------------------------------------
        if self.combo_tier > 1 or self.combo_count:
            self.combo_timer -= dt
            if self.combo_timer <= 0.0:
                self.combo_tier = 1
                self.combo_count = 0

        if self.powerups.active("speed_boost"):
            self.particles.speed_lines(2)

        # --- collision ------------------------------------------------------
        hit = self.field.collide(self.player)
        if hit is not None and not self.powerups.invulnerable():
            if self.powerups.consume_shield(INVULN_AFTER_HIT):
                hit.hit = True
                self._on_shielded(hit)
            else:
                self._on_death(hit)
                return None

        # --- finish ---------------------------------------------------------
        if self.travelled >= self.plan.distance_units:
            self.travelled = self.plan.distance_units
            self.finished = True
            if self.audio:
                self.audio.play("complete")
            return "completed"
        return None

    def _update_dying(self, dt: float) -> Optional[str]:
        self.dying = max(0.0, self.dying - dt)
        # Coast to a stop rather than freezing dead in the road.
        self.base_speed = max(0.0, self.base_speed - self.base_speed * 3.2 * dt - 60.0 * dt)
        self.speed = self.base_speed
        self.travelled += self.speed * dt
        self.player.update(dt, self.speed, None)
        self.renderer.update(dt, self.speed, self.travelled)
        self.field.set_travelled(self.travelled)
        self.field.update(dt, self.speed, self.travelled, self.elapsed)
        if self.dying <= 0.0:
            self.dead = True
            return "died"
        return None

    # ----------------------------------------------------------------- events
    def _combo_mult(self) -> float:
        return 1.0 + (self.combo_tier - 1) * COMBO_TIER_STEP

    def _bank(self, points: float) -> None:
        self.earned_score += points * self._combo_mult() * self.score_mult

    def _on_dodge(self, count: int) -> None:
        self.dodges += count
        self._bank(SCORE_PER_DODGE * count)
        self.combo_timer = COMBO_TIMEOUT
        self.combo_count += count
        while self.combo_count >= COMBO_STEP and self.combo_tier < COMBO_MAX_TIER:
            self.combo_count -= COMBO_STEP
            self.combo_tier += 1
            self.best_tier = max(self.best_tier, self.combo_tier)
            if self.audio:
                self.audio.play("combo", 0.7)

    def _on_coins(self, gained: int) -> None:
        self.coins += gained
        self._bank(SCORE_PER_COIN * gained)
        amount = int(round(gained * self.powerups.coin_mult() * self.coin_bonus))
        if amount > 0:
            self.wallet.add(amount, "run")
            self.down_earned += amount
        if self.audio:
            self.audio.play("coin", 0.55)
        sx, sy, scale = self.player.screen_pos()
        self.particles.coin_sparkle(sx, sy - PLAYER_H * 0.5 * scale, 5)

    def _on_powerup(self, kind: str) -> None:
        self.pu_taken += 1
        self.powerups.activate(kind)
        self._bank(SCORE_PER_POWERUP)
        if self.audio:
            self.audio.play("powerup")
        sx, sy, scale = self.player.screen_pos()
        self.particles.ring(sx, sy - PLAYER_H * 0.5 * scale,
                            voxel.POWERUP_COLORS.get(kind, (255, 255, 255)))

    def _on_land(self) -> None:
        sx, sy, scale = self.player.screen_pos()
        self.particles.dust(sx, sy, self.world_spec.get("verge_a", (190, 190, 180)), 8)
        if self.audio:
            self.audio.play("land", 0.5)

    def _on_shielded(self, obs) -> None:
        self.powerups.invuln = INVULN_AFTER_HIT
        self.player.hit_flash = INVULN_AFTER_HIT
        self.shake.kick(16.0)
        sx, sy, scale = self.player.screen_pos()
        self.particles.hit_burst(sx, sy - PLAYER_H * 0.5 * scale, (120, 200, 255))
        if self.audio:
            self.audio.play("shield")

    def _on_death(self, obs) -> None:
        self.player.alive = False
        self.player.hit_flash = DEATH_TIME
        self.dying = DEATH_TIME
        self.combo_tier = 1
        self.shake.kick(30.0)
        sx, sy, scale = self.player.screen_pos()
        self.particles.hit_burst(sx, sy - PLAYER_H * 0.5 * scale)
        if self.audio:
            self.audio.play("hit")
            self.audio.play("death", 0.9)

    # --------------------------------------------------------------- readouts
    @property
    def distance_m(self) -> float:
        return min(self.plan.distance_m, self.travelled / METER) if self.plan else 0.0

    @property
    def score(self) -> int:
        return int(self.distance_m * SCORE_PER_METER * self.score_mult + self.earned_score)

    @property
    def progress(self) -> float:
        if not self.plan or self.plan.distance_units <= 0:
            return 0.0
        return max(0.0, min(1.0, self.travelled / self.plan.distance_units))

    def result(self) -> Dict[str, object]:
        """Everything the game-over / level-complete screens and stats need."""
        plan = self.plan
        score = self.score
        return {
            "level": self.level,
            "completed": self.finished,
            "score": score,
            "stars": plan.stars_for(score) if (plan and self.finished) else 0,
            "coins": self.coins,
            "down": self.down_earned,
            "distance_m": int(self.distance_m),
            "target_m": int(plan.distance_m) if plan else 0,
            "dodges": self.dodges,
            "powerups": self.pu_taken,
            "best_combo": self.best_tier,
            "jumps": self.player.jumps,
            "slides": self.player.slides,
            "progress": self.progress,
            "reward": plan.reward if plan else 0,
        }

    # ------------------------------------------------------------------- draw
    def draw(self, surf: pygame.Surface) -> None:
        if not self.started or self.renderer is None:
            return
        shake = self.shake.offset()

        self.renderer.draw(surf, self.travelled, self.speed, shake)
        # Anything still ahead of the player, far to near.
        self.field.draw(surf, self.travelled, self.speed, shake, passed=False)
        self.items.draw(surf, self.travelled, self.speed, self.elapsed, shake)
        self._draw_finish(surf, shake)

        self.player.draw(surf, shake)
        if self.powerups.active("shield"):
            self._draw_shield(surf, shake)

        # Obstacles the player has just gone past are nearer than the player, so
        # they belong on top of the sprite.
        self.field.draw(surf, self.travelled, self.speed, shake, passed=True)
        self.particles.draw(surf)

    def _draw_shield(self, surf: pygame.Surface, shake: Tuple[float, float]) -> None:
        sx, sy, scale = self.player.screen_pos()
        size = int(PLAYER_H * 1.9 * scale)
        bubble = voxel.shield_bubble(size)
        pulse = 0.75 + 0.25 * math.sin(self.elapsed * 7.0)
        bubble.set_alpha(int(190 * pulse * min(1.0, self.powerups.fraction("shield") * 3.0 + 0.35)))
        surf.blit(bubble, (sx - size / 2 + shake[0],
                           sy - size * 0.62 + shake[1]))

    def _draw_finish(self, surf: pygame.Surface, shake: Tuple[float, float]) -> None:
        if self.plan is None:
            return
        z = self.plan.distance_units - self.travelled
        far = camera.draw_z(self.speed)
        if z <= NEAR_Z or z > far:
            return
        scale = camera.scale_at(z)
        h = int(FINISH_GATE_H * scale)
        if h < 8:
            return
        w = int(h * 240 / 150)
        gate = voxel.finish_gate(w, h)
        x = camera.screen_x(0.0, z) + shake[0]
        y = camera.ground_y(z) + shake[1]
        surf.blit(gate, (x - w / 2, y - h))
