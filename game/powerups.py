"""
powerups.py - The six power-ups, their timers and their upgrade economics.

Duration stacks three ways, all of which already exist as data:

    POWERUP_BASE_TIME[kind]                     the designed baseline
    x (1 + POWERUP_UPGRADE_STEP * (level - 1))  what the player bought
    x (1 + character bonus)                     who the player is wearing

The manager owns nothing but timers. What it *means* to have a power-up active
is read back out by run.py through the small query methods at the bottom, so
there is exactly one place each effect is applied.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from player import character_bonus
from settings import (
    COIN_MULT_VALUE,
    MAGNET_RANGE,
    POWERUP_BASE_TIME,
    POWERUP_MAX_LEVEL,
    POWERUP_UPGRADE_COST,
    POWERUP_UPGRADE_STEP,
    SLOWMO_MULT,
    SPEED_BOOST_MULT,
)

KINDS: Tuple[str, ...] = tuple(POWERUP_BASE_TIME.keys())

INFO: Dict[str, dict] = {
    "magnet": {
        "name": "Magnet",
        "desc": "Pulls nearby DOWN straight to you.",
    },
    "shield": {
        "name": "Shield",
        "desc": "Absorbs one hit instead of ending the run.",
    },
    "coin_multiplier": {
        "name": "Coin Multiplier",
        "desc": f"Every coin is worth {COIN_MULT_VALUE}x DOWN.",
    },
    "speed_boost": {
        "name": "Speed Boost",
        "desc": "Surge forward - more distance, more risk.",
    },
    "super_jump": {
        "name": "Super Jump",
        "desc": "Jump markedly higher.",
    },
    "slow_motion": {
        "name": "Slow Motion",
        "desc": "Slows the world down so you can read it.",
    },
}


def display_name(kind: str) -> str:
    return INFO.get(kind, {}).get("name", kind.replace("_", " ").title())


def description(kind: str) -> str:
    return INFO.get(kind, {}).get("desc", "")


def upgrade_cost(current_level: int) -> Optional[int]:
    """DOWN to go from ``current_level`` to the next one, or None if maxed.

    Index 0 of POWERUP_UPGRADE_COST is a level-zero placeholder, and the final
    entry is spare headroom for a future cap raise.
    """
    current_level = max(1, int(current_level))
    if current_level >= POWERUP_MAX_LEVEL:
        return None
    if current_level < len(POWERUP_UPGRADE_COST):
        return int(POWERUP_UPGRADE_COST[current_level])
    return int(POWERUP_UPGRADE_COST[-1])


def duration_for(kind: str, level: int, character_id: str = "starter") -> float:
    """Full duration in seconds, with upgrades and character bonuses applied."""
    base = float(POWERUP_BASE_TIME.get(kind, 8.0))
    level = max(1, min(POWERUP_MAX_LEVEL, int(level)))
    out = base * (1.0 + POWERUP_UPGRADE_STEP * (level - 1))
    out *= 1.0 + float(character_bonus(character_id, "powerup_dur", 0.0))
    if kind == "shield":
        out *= 1.0 + float(character_bonus(character_id, "shield_dur", 0.0))
    return out


class PowerupManager:
    """Live power-up timers for one run."""

    def __init__(self, save, character_id: str = "starter") -> None:
        self.save = save
        self.character_id = character_id
        self.timers: Dict[str, float] = {}
        self.totals: Dict[str, float] = {}
        self.shield_ready = False
        self.invuln = 0.0
        self.collected = 0
        self.just_activated: List[str] = []

    # ------------------------------------------------------------- lifecycle
    def reset(self, character_id: Optional[str] = None) -> None:
        if character_id:
            self.character_id = character_id
        self.timers.clear()
        self.totals.clear()
        self.shield_ready = False
        self.invuln = 0.0
        self.collected = 0
        self.just_activated.clear()
        # Some characters start a run already shielded.
        if character_bonus(self.character_id, "start_shield", False):
            self.activate("shield", count=False)

    def duration(self, kind: str) -> float:
        level = self.save.powerup_level(kind) if self.save else 1
        return duration_for(kind, level, self.character_id)

    def activate(self, kind: str, count: bool = True) -> None:
        if kind not in POWERUP_BASE_TIME:
            return
        total = self.duration(kind)
        # Re-collecting refreshes rather than stacks, but never shortens.
        self.timers[kind] = max(self.timers.get(kind, 0.0), total)
        self.totals[kind] = total
        if kind == "shield":
            self.shield_ready = True
        if count:
            self.collected += 1
            self.just_activated.append(kind)

    def update(self, dt: float) -> List[str]:
        """Tick timers. Returns kinds that expired this frame."""
        expired: List[str] = []
        for kind in list(self.timers.keys()):
            self.timers[kind] -= dt
            if self.timers[kind] <= 0.0:
                del self.timers[kind]
                self.totals.pop(kind, None)
                if kind == "shield":
                    self.shield_ready = False
                expired.append(kind)
        if self.invuln > 0.0:
            self.invuln = max(0.0, self.invuln - dt)
        return expired

    def drain_activations(self) -> List[str]:
        out = list(self.just_activated)
        self.just_activated.clear()
        return out

    # ----------------------------------------------------------------- state
    def active(self, kind: str) -> bool:
        return self.timers.get(kind, 0.0) > 0.0

    def remaining(self, kind: str) -> float:
        return max(0.0, self.timers.get(kind, 0.0))

    def fraction(self, kind: str) -> float:
        total = self.totals.get(kind, 0.0)
        if total <= 0.0:
            return 0.0
        return max(0.0, min(1.0, self.timers.get(kind, 0.0) / total))

    def active_kinds(self) -> List[str]:
        """Longest-remaining first, so the HUD ordering is stable."""
        return sorted(self.timers.keys(), key=lambda k: -self.timers[k])

    # --------------------------------------------------------------- effects
    def speed_mult(self) -> float:
        mult = 1.0
        if self.active("speed_boost"):
            mult *= SPEED_BOOST_MULT
        if self.active("slow_motion"):
            mult *= SLOWMO_MULT
        return mult

    def coin_mult(self) -> int:
        return COIN_MULT_VALUE if self.active("coin_multiplier") else 1

    def magnet_range(self) -> float:
        if not self.active("magnet"):
            return 0.0
        return MAGNET_RANGE * (1.0 + float(character_bonus(self.character_id, "magnet_range", 0.0)))

    def super_jump(self) -> bool:
        return self.active("super_jump")

    def consume_shield(self, invuln: float) -> bool:
        """Spend the shield on a hit. True if the run survives."""
        if not self.shield_ready:
            return False
        self.shield_ready = False
        self.timers.pop("shield", None)
        self.totals.pop("shield", None)
        self.invuln = invuln
        return True

    def invulnerable(self) -> bool:
        return self.invuln > 0.0
