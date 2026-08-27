"""
player.py - The runner, plus the catalogue of original voxel characters.

The player occupies a fixed depth (z = 0); the world scrolls toward them. All
state is time-based (delta time), so behaviour is identical at any frame rate.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame

import voxel
from settings import (
    CAM_HEIGHT,
    CAM_Z,
    COYOTE_TIME,
    FOCAL,
    GRAVITY,
    HORIZON_Y,
    INPUT_BUFFER,
    JUMP_V,
    LANE_SWITCH_TIME,
    LANE_X,
    PLAYER_D,
    PLAYER_H,
    PLAYER_W,
    RARITY_PRICE,
    SLIDE_H_FACTOR,
    SLIDE_TIME,
    SUPER_JUMP_MULT,
    CX,
)

# --------------------------------------------------------------------------
# Character catalogue
#
# All designs are original blocky figures built from cubes (see voxel.py).
# ``bonus`` values are deliberately small: rarity buys looks and a nudge, never
# a win button.
# --------------------------------------------------------------------------

CHARACTERS: List[dict] = [
    {
        "id": "starter", "name": "Blocky Bo", "rarity": "COMMON", "price": 0,
        "desc": "Where every adventure begins.",
        "bonus": {},
        "spec": {"skin": (236, 194, 152), "shirt": (74, 152, 226), "pants": (58, 66, 92),
                 "shoes": (44, 40, 40), "accent": (250, 224, 120), "head_style": "hair",
                 "accent2": (120, 90, 60)},
    },
    {
        "id": "forest_explorer", "name": "Forest Explorer", "rarity": "COMMON",
        "desc": "Knows every leaf in the valley.", "bonus": {"coin_mult": 0.03},
        "spec": {"skin": (226, 182, 140), "shirt": (72, 142, 84), "pants": (86, 70, 48),
                 "shoes": (54, 42, 32), "accent": (196, 226, 132), "head_style": "hat",
                 "backpack": (120, 92, 56)},
    },
    {
        "id": "miner", "name": "Deep Miner", "rarity": "COMMON",
        "desc": "Digs up a little extra DOWN.", "bonus": {"coin_mult": 0.04},
        "spec": {"skin": (222, 178, 138), "shirt": (128, 108, 90), "pants": (76, 84, 104),
                 "shoes": (52, 46, 42), "accent": (255, 206, 74), "head_style": "helmet",
                 "backpack": (96, 96, 104)},
    },
    {
        "id": "pixel_scout", "name": "Pixel Scout", "rarity": "COMMON",
        "desc": "Small steps, quick feet.", "bonus": {"score_mult": 0.03},
        "spec": {"skin": (240, 200, 160), "shirt": (226, 118, 82), "pants": (62, 74, 96),
                 "shoes": (48, 44, 44), "accent": (255, 232, 150), "head_style": "band"},
    },
    {
        "id": "adventurer", "name": "Adventurer", "rarity": "UNCOMMON",
        "desc": "Built for the long run.", "bonus": {"coin_mult": 0.05},
        "spec": {"skin": (232, 188, 146), "shirt": (198, 158, 78), "pants": (92, 74, 54),
                 "shoes": (58, 46, 36), "accent": (255, 226, 150), "head_style": "hat",
                 "backpack": (146, 110, 66)},
    },
    {
        "id": "knight", "name": "Iron Knight", "rarity": "UNCOMMON",
        "desc": "Shields hold a little longer.", "bonus": {"shield_dur": 0.10},
        "spec": {"skin": (226, 186, 148), "shirt": (176, 184, 202), "pants": (128, 136, 154),
                 "shoes": (72, 76, 88), "accent": (222, 230, 246), "head_style": "helmet",
                 "cape": (188, 62, 72), "sword": (206, 214, 232)},
    },
    {
        "id": "pirate", "name": "Block Pirate", "rarity": "UNCOMMON",
        "desc": "Treasure sense in the bones.", "bonus": {"magnet_range": 0.12},
        "spec": {"skin": (226, 180, 138), "shirt": (188, 74, 78), "pants": (54, 58, 74),
                 "shoes": (56, 44, 36), "accent": (250, 240, 220), "head_style": "band",
                 "sword": (214, 220, 230)},
    },
    {
        "id": "ninja", "name": "Shadow Ninja", "rarity": "RARE",
        "desc": "Silent, swift, stylish.", "bonus": {"score_mult": 0.06, "jump_boost": 0.03},
        "spec": {"skin": (86, 90, 110), "shirt": (44, 48, 66), "pants": (36, 40, 56),
                 "shoes": (26, 28, 40), "accent": (226, 62, 82), "head_style": "hood"},
    },
    {
        "id": "robot", "name": "Voxel Bot", "rarity": "RARE",
        "desc": "Precision-machined for speed.", "bonus": {"score_mult": 0.05, "coin_mult": 0.03},
        "spec": {"skin": (176, 186, 202), "shirt": (108, 118, 138), "pants": (84, 92, 110),
                 "shoes": (60, 66, 80), "accent": (92, 226, 255), "head_style": "visor",
                 "glow": (60, 180, 220)},
    },
    {
        "id": "desert_warrior", "name": "Desert Warrior", "rarity": "RARE",
        "desc": "Thrives where the sand burns.", "bonus": {"coin_mult": 0.07},
        "spec": {"skin": (206, 158, 112), "shirt": (222, 190, 128), "pants": (168, 132, 84),
                 "shoes": (108, 82, 52), "accent": (238, 214, 160), "head_style": "hood",
                 "cape": (216, 186, 128)},
    },
    {
        "id": "alien", "name": "Cube Alien", "rarity": "RARE",
        "desc": "Not from this block.", "bonus": {"jump_boost": 0.07},
        "spec": {"skin": (146, 226, 146), "shirt": (90, 190, 160), "pants": (58, 132, 122),
                 "shoes": (40, 96, 92), "accent": (216, 255, 180), "head_style": "horns",
                 "glow": (110, 240, 160)},
    },
    {
        "id": "engineer", "name": "Gear Engineer", "rarity": "RARE",
        "desc": "Tunes power-ups to last.", "bonus": {"powerup_dur": 0.08},
        "spec": {"skin": (228, 184, 142), "shirt": (150, 108, 68), "pants": (96, 88, 78),
                 "shoes": (62, 52, 44), "accent": (214, 168, 88), "head_style": "hat",
                 "backpack": (130, 118, 96)},
    },
    {
        "id": "fire_warrior", "name": "Fire Warrior", "rarity": "EPIC",
        "desc": "Leaves embers in the lane.", "bonus": {"score_mult": 0.08, "coin_mult": 0.04},
        "spec": {"skin": (232, 158, 118), "shirt": (214, 78, 46), "pants": (128, 54, 38),
                 "shoes": (74, 36, 28), "accent": (255, 186, 74), "head_style": "horns",
                 "cape": (232, 116, 44), "glow": (240, 120, 40)},
    },
    {
        "id": "ice_warrior", "name": "Ice Warrior", "rarity": "EPIC",
        "desc": "Cool head, steady run.", "bonus": {"shield_dur": 0.16},
        "spec": {"skin": (206, 226, 244), "shirt": (108, 186, 226), "pants": (72, 130, 180),
                 "shoes": (52, 92, 132), "accent": (222, 246, 255), "head_style": "crown",
                 "cape": (150, 214, 246), "glow": (120, 200, 255)},
    },
    {
        "id": "shadow", "name": "Shadow", "rarity": "EPIC",
        "desc": "Barely there at all.", "bonus": {"score_mult": 0.10},
        "spec": {"skin": (58, 58, 78), "shirt": (36, 36, 52), "pants": (28, 28, 42),
                 "shoes": (20, 20, 32), "accent": (140, 96, 226), "head_style": "hood",
                 "cape": (46, 40, 70), "glow": (110, 70, 200)},
    },
    {
        "id": "samurai", "name": "Block Samurai", "rarity": "EPIC",
        "desc": "One clean line through chaos.", "bonus": {"score_mult": 0.06, "shield_dur": 0.08},
        "spec": {"skin": (230, 190, 150), "shirt": (168, 52, 60), "pants": (54, 52, 66),
                 "shoes": (40, 36, 40), "accent": (240, 226, 190), "head_style": "helmet",
                 "cape": (198, 74, 78), "sword": (226, 232, 240)},
    },
    {
        "id": "yeti", "name": "Snow Yeti", "rarity": "EPIC",
        "desc": "Big feet, bigger jumps.", "bonus": {"jump_boost": 0.10},
        "spec": {"skin": (232, 240, 250), "shirt": (206, 222, 240), "pants": (176, 196, 220),
                 "shoes": (132, 152, 180), "accent": (140, 200, 240), "head_style": "hair",
                 "chest_stripe": False},
    },
    {
        "id": "crystal_warrior", "name": "Crystal Warrior", "rarity": "LEGENDARY",
        "desc": "Refracts DOWN toward you.", "bonus": {"magnet_range": 0.20, "coin_mult": 0.06},
        "spec": {"skin": (196, 226, 255), "shirt": (140, 122, 236), "pants": (94, 84, 180),
                 "shoes": (64, 58, 132), "accent": (206, 236, 255), "head_style": "crown",
                 "glow": (150, 140, 255), "wings": (176, 200, 255)},
    },
    {
        "id": "cyber_warrior", "name": "Cyber Warrior", "rarity": "LEGENDARY",
        "desc": "Overclocked and neon-lit.", "bonus": {"score_mult": 0.10, "powerup_dur": 0.06},
        "spec": {"skin": (140, 150, 176), "shirt": (44, 52, 86), "pants": (34, 40, 68),
                 "shoes": (26, 30, 52), "accent": (86, 255, 226), "head_style": "visor",
                 "glow": (60, 240, 220), "cape": (58, 74, 128)},
    },
    {
        "id": "lava_golem", "name": "Lava Golem", "rarity": "LEGENDARY",
        "desc": "Starts each run shielded.", "bonus": {"start_shield": True},
        "spec": {"skin": (86, 62, 58), "shirt": (66, 48, 46), "pants": (52, 38, 36),
                 "shoes": (40, 30, 28), "accent": (255, 128, 40), "head_style": "horns",
                 "glow": (255, 110, 30), "chest_stripe": True},
    },
    {
        "id": "king", "name": "Block King", "rarity": "LEGENDARY",
        "desc": "The valley bows to the crown.", "bonus": {"coin_mult": 0.10, "score_mult": 0.04},
        "spec": {"skin": (234, 192, 152), "shirt": (188, 62, 82), "pants": (86, 62, 96),
                 "shoes": (62, 46, 40), "accent": (255, 214, 96), "head_style": "crown",
                 "cape": (170, 48, 66), "glow": (255, 200, 90)},
    },
    {
        "id": "queen", "name": "Block Queen", "rarity": "LEGENDARY",
        "desc": "Grace at full speed.", "bonus": {"magnet_range": 0.14, "score_mult": 0.06},
        "spec": {"skin": (240, 198, 162), "shirt": (150, 74, 176), "pants": (104, 58, 132),
                 "shoes": (70, 44, 92), "accent": (255, 226, 160), "head_style": "crown",
                 "cape": (188, 106, 210), "glow": (226, 150, 255)},
    },
    {
        "id": "dragon_warrior", "name": "Dragon Warrior", "rarity": "MYTHIC",
        "desc": "Rides the thermals of the peaks.", "bonus": {"coin_mult": 0.12, "score_mult": 0.08,
                                                             "jump_boost": 0.06},
        "spec": {"skin": (196, 150, 118), "shirt": (72, 152, 108), "pants": (54, 106, 82),
                 "shoes": (42, 74, 60), "accent": (255, 196, 82), "head_style": "horns",
                 "wings": (96, 196, 140), "glow": (120, 240, 170), "sword": (255, 214, 120)},
    },
    {
        "id": "angel", "name": "Sky Guardian", "rarity": "MYTHIC",
        "desc": "Shields that hold, wings that lift.", "bonus": {"shield_dur": 0.22,
                                                                "jump_boost": 0.08,
                                                                "start_shield": True},
        "spec": {"skin": (244, 214, 184), "shirt": (240, 240, 250), "pants": (206, 214, 236),
                 "shoes": (168, 178, 206), "accent": (255, 236, 160), "head_style": "halo",
                 "wings": (250, 250, 255), "glow": (255, 244, 190)},
    },
    {
        "id": "legend", "name": "The Legend", "rarity": "MYTHIC",
        "desc": "Every system, slightly better.", "bonus": {"coin_mult": 0.10, "score_mult": 0.10,
                                                           "magnet_range": 0.10,
                                                           "shield_dur": 0.10,
                                                           "powerup_dur": 0.10},
        "spec": {"skin": (252, 226, 190), "shirt": (255, 186, 60), "pants": (176, 108, 32),
                 "shoes": (108, 66, 24), "accent": (255, 246, 200), "head_style": "crown",
                 "cape": (255, 156, 48), "glow": (255, 200, 80), "wings": (255, 214, 120)},
    },
]

# Fill in prices from the rarity table and index by id.
for _c in CHARACTERS:
    _c.setdefault("price", RARITY_PRICE[_c["rarity"]])
    _c["spec"]["id"] = _c["id"]

CHARACTERS_BY_ID: Dict[str, dict] = {c["id"]: c for c in CHARACTERS}


def get_character(cid: str) -> dict:
    return CHARACTERS_BY_ID.get(cid) or CHARACTERS_BY_ID["starter"]


def character_bonus(cid: str, key: str, default: float = 0.0):
    return get_character(cid).get("bonus", {}).get(key, default)


def bonus_lines(cid: str) -> List[str]:
    """Human-readable perk list for shop cards."""
    labels = {
        "coin_mult": "+{p}% DOWN",
        "score_mult": "+{p}% Score",
        "shield_dur": "+{p}% Shield Time",
        "magnet_range": "+{p}% Magnet Range",
        "powerup_dur": "+{p}% Power-Up Time",
        "jump_boost": "+{p}% Jump Height",
    }
    out: List[str] = []
    for key, value in get_character(cid).get("bonus", {}).items():
        if key == "start_shield" and value:
            out.append("Starts with Shield")
        elif key in labels:
            out.append(labels[key].format(p=int(round(value * 100))))
    return out or ["No passive bonus"]


# --------------------------------------------------------------------------
# Player
# --------------------------------------------------------------------------


class Player:
    """Three-lane runner with jump, slide and buffered, responsive controls."""

    def __init__(self, character_id: str = "starter") -> None:
        self.character_id = character_id
        self.spec = get_character(character_id)["spec"]
        self.reset()

    # ------------------------------------------------------------- lifecycle
    def set_character(self, character_id: str) -> None:
        self.character_id = character_id
        self.spec = get_character(character_id)["spec"]

    def reset(self) -> None:
        self.lane = 1
        self.x = LANE_X[1]
        self._from_x = self.x
        self._to_x = self.x
        self._switch_t = 1.0

        self.y = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.air_time = 0.0
        self.coyote = 0.0

        self.sliding = False
        self.slide_timer = 0.0
        self.slide_cooldown = 0.0
        self.dive = False

        self.buf_jump = 0.0
        self.buf_slide = 0.0
        self.buf_lane = 0

        self.anim = 0.0
        self.alive = True
        self.hit_flash = 0.0
        self.super_jump = False
        self.jump_bonus = 1.0 + float(character_bonus(self.character_id, "jump_boost", 0.0))
        self.jumps = 0
        self.slides = 0
        self.lane_changes = 0

    # ---------------------------------------------------------------- inputs
    def move_left(self) -> None:
        self._request_lane(-1)

    def move_right(self) -> None:
        self._request_lane(1)

    def _request_lane(self, direction: int) -> None:
        target = self.lane + direction
        if 0 <= target <= 2:
            if self._switch_t >= 1.0:
                self._start_switch(target)
            else:
                # Queue one extra hop so fast double-taps feel right.
                self.buf_lane = direction
        else:
            self.buf_lane = 0

    def _start_switch(self, target: int) -> None:
        self.lane = target
        self._from_x = self.x
        self._to_x = LANE_X[target]
        self._switch_t = 0.0
        self.lane_changes += 1

    def jump(self) -> bool:
        if self.sliding:
            self._end_slide()
        if self.on_ground or self.coyote > 0.0:
            self.vy = JUMP_V * self.jump_bonus * (SUPER_JUMP_MULT if self.super_jump else 1.0)
            self.on_ground = False
            self.coyote = 0.0
            self.air_time = 0.0
            self.dive = False
            self.jumps += 1
            self.buf_jump = 0.0
            return True
        self.buf_jump = INPUT_BUFFER
        return False

    def slide(self) -> bool:
        if not self.on_ground:
            # Dive: fall fast, then slide the moment we touch down.
            self.dive = True
            self.vy = min(self.vy, -JUMP_V * 0.85)
            self.buf_slide = INPUT_BUFFER
            return False
        if self.slide_cooldown > 0.0:
            self.buf_slide = INPUT_BUFFER
            return False
        self.sliding = True
        self.slide_timer = SLIDE_TIME
        self.slides += 1
        self.buf_slide = 0.0
        return True

    def _end_slide(self) -> None:
        from settings import SLIDE_COOLDOWN

        self.sliding = False
        self.slide_timer = 0.0
        self.slide_cooldown = SLIDE_COOLDOWN

    # ---------------------------------------------------------------- update
    def update(self, dt: float, speed: float, sfx=None) -> None:
        # Lane tween with ease-out for a snappy but readable slide across lanes.
        if self._switch_t < 1.0:
            self._switch_t = min(1.0, self._switch_t + dt / LANE_SWITCH_TIME)
            t = 1.0 - (1.0 - self._switch_t) ** 3
            self.x = self._from_x + (self._to_x - self._from_x) * t
            if self._switch_t >= 1.0 and self.buf_lane:
                direction, self.buf_lane = self.buf_lane, 0
                target = self.lane + direction
                if 0 <= target <= 2:
                    self._start_switch(target)

        # Vertical motion
        if not self.on_ground:
            gravity = GRAVITY * (1.55 if self.dive else 1.0)
            self.vy -= gravity * dt
            self.y += self.vy * dt
            self.air_time += dt
            if self.y <= 0.0:
                self.y = 0.0
                self.vy = 0.0
                self.on_ground = True
                self.dive = False
                self.air_time = 0.0
                if self.buf_slide > 0.0:
                    self.slide()
        else:
            self.coyote = COYOTE_TIME

        if self.coyote > 0.0 and not self.on_ground:
            self.coyote = max(0.0, self.coyote - dt)

        if self.slide_cooldown > 0.0:
            self.slide_cooldown = max(0.0, self.slide_cooldown - dt)

        if self.sliding:
            self.slide_timer -= dt
            if self.slide_timer <= 0.0:
                self._end_slide()

        # Buffered inputs
        if self.buf_jump > 0.0:
            self.buf_jump -= dt
            if self.on_ground or self.coyote > 0.0:
                if self.jump() and sfx:
                    sfx("jump")
        if self.buf_slide > 0.0:
            self.buf_slide -= dt

        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)

        # Run cycle speeds up with the world.
        self.anim += dt * (5.4 + speed / 260.0)

    # ------------------------------------------------------------- collision
    @property
    def height(self) -> float:
        return PLAYER_H * (SLIDE_H_FACTOR if self.sliding else 1.0)

    def hitbox(self) -> Tuple[float, float, float, float, float, float]:
        """(x0, x1, y0, y1, z0, z1) in world units."""
        half_w = PLAYER_W * 0.5
        half_d = PLAYER_D * 0.5
        return (
            self.x - half_w, self.x + half_w,
            self.y, self.y + self.height,
            -half_d, half_d,
        )

    @property
    def pose(self) -> str:
        if self.hit_flash > 0.0 and not self.alive:
            return "hit"
        if self.sliding:
            return "slide"
        if not self.on_ground:
            return "jump"
        return "run"

    # ------------------------------------------------------------------ draw
    def screen_pos(self) -> Tuple[float, float, float]:
        scale = FOCAL / CAM_Z
        sx = CX + self.x * scale
        sy = HORIZON_Y + (CAM_HEIGHT - self.y) * scale
        return sx, sy, scale

    def draw(self, surf: pygame.Surface, shake: Tuple[float, float] = (0.0, 0.0),
             shadow: bool = True) -> None:
        sx, sy, scale = self.screen_pos()
        sx += shake[0]
        sy += shake[1]

        if shadow:
            ground_y = HORIZON_Y + CAM_HEIGHT * scale + shake[1]
            lift = min(1.0, self.y / 190.0)
            sw = int(PLAYER_W * scale * (1.0 - lift * 0.42))
            sh = max(4, int(sw * 0.3))
            alpha = int(120 * (1.0 - lift * 0.7))
            shadow_surf = voxel.CACHE.scaled(
                "player_shadow",
                lambda: _shadow_surface(),
                max(8, sw), max(4, sh),
            )
            shadow_surf.set_alpha(alpha)
            surf.blit(shadow_surf, (sx - sw / 2, ground_y - sh / 2))

        pose = self.pose
        if pose == "slide":
            vis_h = PLAYER_H * 0.62
            vis_w = vis_h * 1.35
        else:
            vis_h = PLAYER_H * 1.05
            vis_w = vis_h * (voxel.CHAR_W / voxel.CHAR_H)
        w = int(vis_w * scale)
        h = int(vis_h * scale)
        frame = int(self.anim) % voxel.RUN_FRAMES
        sprite = voxel.character_sprite(self.spec, pose, frame, w, h)

        if self.hit_flash > 0.0 and int(self.hit_flash * 20) % 2 == 0:
            sprite = sprite.copy()
            sprite.fill((255, 120, 120, 0), special_flags=pygame.BLEND_RGBA_ADD)

        surf.blit(sprite, (sx - w / 2, sy - h))


def _shadow_surface() -> pygame.Surface:
    s = voxel.make_surface(64, 24)
    pygame.draw.ellipse(s, (0, 0, 0, 255), (0, 0, 64, 24))
    return s
