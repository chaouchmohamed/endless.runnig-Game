"""
achievements.py - Long-run goals, checked against the save file.

Each achievement is a predicate over the SaveManager, so nothing needs its own
counter: the eleven ``stats`` keys and the progression data the save already
tracks are enough. ``refresh`` re-evaluates every predicate and returns whatever
newly completed, which the game turns into a toast.

The stored shape matches save_system's default exactly:
``achievements: {id: {"done": bool, "claimed": bool}}``
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import player as player_mod
import world as world_mod
from settings import COMBO_MAX_TIER, FINAL_LEVEL, POWERUP_BASE_TIME, POWERUP_MAX_LEVEL


# --------------------------------------------------------------------------
# Helpers used by the predicates
# --------------------------------------------------------------------------


def total_stars(save) -> int:
    return sum(int(r.get("stars", 0)) for r in save.data["levels_completed"].values())


def three_star_levels(save) -> int:
    return sum(1 for r in save.data["levels_completed"].values()
               if int(r.get("stars", 0)) >= 3)


def maxed_powerups(save) -> int:
    return sum(1 for k in POWERUP_BASE_TIME
               if save.powerup_level(k) >= POWERUP_MAX_LEVEL)


def _stat(save, key: str) -> float:
    try:
        return float(save.stats.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# Catalogue
#
# ``progress`` is optional and only drives the bar in the UI; ``check`` is
# what actually decides completion.
# --------------------------------------------------------------------------

ACHIEVEMENTS: List[dict] = [
    {"id": "first_adventure", "name": "First Adventure",
     "desc": "Complete level 1.", "reward": 200,
     "check": lambda s: s.is_level_complete(1)},
    {"id": "getting_going", "name": "Getting Going",
     "desc": "Complete level 10.", "reward": 500,
     "check": lambda s: s.is_level_complete(10)},
    {"id": "quarter_way", "name": "Quarter Way",
     "desc": "Complete level 50.", "reward": 2_000,
     "check": lambda s: s.is_level_complete(50)},
    {"id": "halfway_hero", "name": "Halfway Hero",
     "desc": "Complete level 100.", "reward": 6_000,
     "check": lambda s: s.is_level_complete(100)},
    {"id": "the_legend", "name": "The Legend",
     "desc": f"Complete level {FINAL_LEVEL}.", "reward": 40_000,
     "check": lambda s: s.is_level_complete(FINAL_LEVEL)},

    {"id": "pocket_change", "name": "Pocket Change",
     "desc": "Earn 1,000 DOWN in total.", "reward": 300,
     "check": lambda s: s.data.get("lifetime_down", 0) >= 1_000,
     "progress": lambda s: (s.data.get("lifetime_down", 0), 1_000)},
    {"id": "well_off", "name": "Well Off",
     "desc": "Earn 10,000 DOWN in total.", "reward": 1_200,
     "check": lambda s: s.data.get("lifetime_down", 0) >= 10_000,
     "progress": lambda s: (s.data.get("lifetime_down", 0), 10_000)},
    {"id": "down_tycoon", "name": "DOWN Tycoon",
     "desc": "Earn 100,000 DOWN in total.", "reward": 8_000,
     "check": lambda s: s.data.get("lifetime_down", 0) >= 100_000,
     "progress": lambda s: (s.data.get("lifetime_down", 0), 100_000)},

    {"id": "wardrobe", "name": "Wardrobe",
     "desc": "Own 5 characters.", "reward": 600,
     "check": lambda s: len(s.data["characters_owned"]) >= 5,
     "progress": lambda s: (len(s.data["characters_owned"]), 5)},
    {"id": "full_roster", "name": "Full Roster",
     "desc": "Own 12 characters.", "reward": 3_000,
     "check": lambda s: len(s.data["characters_owned"]) >= 12,
     "progress": lambda s: (len(s.data["characters_owned"]), 12)},
    {"id": "everyone", "name": "Everyone",
     "desc": "Own every character.", "reward": 25_000,
     "check": lambda s: len(s.data["characters_owned"]) >= len(player_mod.CHARACTERS),
     "progress": lambda s: (len(s.data["characters_owned"]), len(player_mod.CHARACTERS))},
    {"id": "globetrotter", "name": "Globetrotter",
     "desc": "Own every world.", "reward": 20_000,
     "check": lambda s: len(s.data["worlds_owned"]) >= len(world_mod.WORLDS),
     "progress": lambda s: (len(s.data["worlds_owned"]), len(world_mod.WORLDS))},

    {"id": "combo_master", "name": "Combo Master",
     "desc": f"Reach combo tier {COMBO_MAX_TIER}.", "reward": 2_500,
     "check": lambda s: _stat(s, "best_combo") >= COMBO_MAX_TIER,
     "progress": lambda s: (int(_stat(s, "best_combo")), COMBO_MAX_TIER)},
    {"id": "star_collector", "name": "Star Collector",
     "desc": "Earn 50 stars.", "reward": 3_000,
     "check": lambda s: total_stars(s) >= 50,
     "progress": lambda s: (total_stars(s), 50)},
    {"id": "perfectionist", "name": "Perfectionist",
     "desc": "Earn 3 stars on 25 levels.", "reward": 6_000,
     "check": lambda s: three_star_levels(s) >= 25,
     "progress": lambda s: (three_star_levels(s), 25)},

    {"id": "marathon", "name": "Marathon",
     "desc": "Run 100,000 metres in total.", "reward": 5_000,
     "check": lambda s: _stat(s, "total_distance") >= 100_000,
     "progress": lambda s: (int(_stat(s, "total_distance")), 100_000)},
    {"id": "jumper", "name": "Spring Loaded",
     "desc": "Jump 1,000 times.", "reward": 800,
     "check": lambda s: _stat(s, "jumps") >= 1_000,
     "progress": lambda s: (int(_stat(s, "jumps")), 1_000)},
    {"id": "slider", "name": "Under Pressure",
     "desc": "Slide 500 times.", "reward": 800,
     "check": lambda s: _stat(s, "slides") >= 500,
     "progress": lambda s: (int(_stat(s, "slides")), 500)},
    {"id": "dodger", "name": "Untouchable",
     "desc": "Dodge 5,000 obstacles.", "reward": 2_500,
     "check": lambda s: _stat(s, "obstacles_dodged") >= 5_000,
     "progress": lambda s: (int(_stat(s, "obstacles_dodged")), 5_000)},
    {"id": "powered_up", "name": "Powered Up",
     "desc": "Collect 250 power-ups.", "reward": 1_500,
     "check": lambda s: _stat(s, "powerups_collected") >= 250,
     "progress": lambda s: (int(_stat(s, "powerups_collected")), 250)},

    {"id": "regular", "name": "Regular",
     "desc": "Start 100 runs.", "reward": 1_200,
     "check": lambda s: _stat(s, "runs") >= 100,
     "progress": lambda s: (int(_stat(s, "runs")), 100)},
    {"id": "persistent", "name": "Persistent",
     "desc": "Get back up 50 times.", "reward": 400,
     "check": lambda s: _stat(s, "deaths") >= 50,
     "progress": lambda s: (int(_stat(s, "deaths")), 50)},
    {"id": "fully_charged", "name": "Fully Charged",
     "desc": "Take one power-up to max level.", "reward": 3_000,
     "check": lambda s: maxed_powerups(s) >= 1,
     "progress": lambda s: (maxed_powerups(s), 1)},
    {"id": "maxed_out", "name": "Maxed Out",
     "desc": "Take every power-up to max level.", "reward": 30_000,
     "check": lambda s: maxed_powerups(s) >= len(POWERUP_BASE_TIME),
     "progress": lambda s: (maxed_powerups(s), len(POWERUP_BASE_TIME))},
]

BY_ID: Dict[str, dict] = {a["id"]: a for a in ACHIEVEMENTS}


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------


def _entry(save, aid: str) -> dict:
    block = save.data.setdefault("achievements", {})
    entry = block.get(aid)
    if not isinstance(entry, dict):
        entry = {"done": False, "claimed": False}
        block[aid] = entry
    entry.setdefault("done", False)
    entry.setdefault("claimed", False)
    return entry


def refresh(save) -> List[dict]:
    """Re-evaluate every achievement. Returns the ones that just completed."""
    unlocked: List[dict] = []
    for spec in ACHIEVEMENTS:
        entry = _entry(save, spec["id"])
        if entry["done"]:
            continue
        try:
            done = bool(spec["check"](save))
        except Exception:
            done = False
        if done:
            entry["done"] = True
            save.mark_dirty()
            unlocked.append(spec)
    return unlocked


def status(save) -> List[dict]:
    """Display-ready list, unclaimed-and-done first so rewards are obvious."""
    out: List[dict] = []
    for spec in ACHIEVEMENTS:
        entry = _entry(save, spec["id"])
        current, target = 0, 1
        getter = spec.get("progress")
        if getter:
            try:
                current, target = getter(save)
            except Exception:
                current, target = 0, 1
        elif entry["done"]:
            current, target = 1, 1
        out.append({
            "id": spec["id"],
            "name": spec["name"],
            "desc": spec["desc"],
            "reward": int(spec["reward"]),
            "done": bool(entry["done"]),
            "claimed": bool(entry["claimed"]),
            "current": int(min(current, target)) if target else 0,
            "target": int(target) if target else 1,
            "fraction": 1.0 if entry["done"] else (
                0.0 if not target else max(0.0, min(1.0, current / target))),
        })
    out.sort(key=lambda a: (a["claimed"], not a["done"]))
    return out


def claim(save, wallet, aid: str) -> Optional[int]:
    """Pay out one completed achievement. Returns the reward, or None."""
    spec = BY_ID.get(aid)
    if not spec:
        return None
    entry = _entry(save, aid)
    if not entry["done"] or entry["claimed"]:
        return None
    entry["claimed"] = True
    reward = int(spec["reward"])
    wallet.add(reward, "achievement")
    save.mark_dirty()
    return reward


def claimable_count(save) -> int:
    return sum(1 for a in status(save) if a["done"] and not a["claimed"])


def claim_all(save, wallet) -> int:
    """Claim everything available. Returns the total paid."""
    total = 0
    for spec in ACHIEVEMENTS:
        got = claim(save, wallet, spec["id"])
        if got:
            total += got
    return total
