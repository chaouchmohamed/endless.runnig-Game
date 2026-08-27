"""
missions.py - Three daily missions, stable for the whole day.

The save file already defines the shape (``missions: {date, list}``), so this
module only supplies the templates and the progress rules.

The day's three missions are drawn with an RNG seeded from the ISO date, which
means they are the same all day, survive a restart, and need nothing stored
beyond the date itself.

Two tracking modes:
  total - accumulates across every run until the mission is done
  best  - keeps the best single run, for "in one run" missions
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from settings import COMBO_MAX_TIER

DAILY_COUNT = 3

# ``key`` names a field of run.RunSession.result(), except for the two synthetic
# keys handled in record_run / record_spend below.
TEMPLATES: List[dict] = [
    {"id": "coins_total", "desc": "Collect {t} DOWN coins", "target": 150,
     "reward": 450, "key": "coins", "mode": "total"},
    {"id": "distance_total", "desc": "Run {t} metres", "target": 3000,
     "reward": 500, "key": "distance_m", "mode": "total"},
    {"id": "dodge_total", "desc": "Dodge {t} obstacles", "target": 70,
     "reward": 480, "key": "dodges", "mode": "total"},
    {"id": "jump_total", "desc": "Jump {t} times", "target": 50,
     "reward": 380, "key": "jumps", "mode": "total"},
    {"id": "slide_total", "desc": "Slide {t} times", "target": 30,
     "reward": 380, "key": "slides", "mode": "total"},
    {"id": "powerup_total", "desc": "Collect {t} power-ups", "target": 8,
     "reward": 520, "key": "powerups", "mode": "total"},
    {"id": "levels_total", "desc": "Complete {t} levels", "target": 3,
     "reward": 700, "key": "completed", "mode": "total"},
    {"id": "stars_total", "desc": "Earn {t} stars", "target": 6,
     "reward": 750, "key": "stars", "mode": "total"},
    {"id": "combo_best", "desc": "Reach combo tier {t}", "target": 4,
     "reward": 600, "key": "best_combo", "mode": "best"},
    {"id": "run_coins_best", "desc": "Collect {t} coins in one run", "target": 70,
     "reward": 620, "key": "coins", "mode": "best"},
    {"id": "run_distance_best", "desc": "Run {t} metres in one run", "target": 1100,
     "reward": 640, "key": "distance_m", "mode": "best"},
    {"id": "run_dodge_best", "desc": "Dodge {t} obstacles in one run", "target": 35,
     "reward": 600, "key": "dodges", "mode": "best"},
    {"id": "three_star", "desc": "Earn 3 stars on {t} level(s)", "target": 1,
     "reward": 800, "key": "_three_star", "mode": "total"},
    {"id": "spend_down", "desc": "Spend {t} DOWN in the shop", "target": 2500,
     "reward": 560, "key": "_spend", "mode": "total"},
]

TEMPLATES_BY_ID: Dict[str, dict] = {t["id"]: t for t in TEMPLATES}


def describe(template: dict) -> str:
    return str(template["desc"]).format(t=f"{template['target']:,}")


# --------------------------------------------------------------------------
# Daily roll
# --------------------------------------------------------------------------


def _roll(date_iso: str) -> List[dict]:
    """The three missions for a given date - deterministic from the date."""
    rng = random.Random(f"missions:{date_iso}")
    picked = rng.sample(TEMPLATES, min(DAILY_COUNT, len(TEMPLATES)))
    return [{"id": t["id"], "progress": 0, "claimed": False} for t in picked]


def ensure_today(save) -> bool:
    """Roll a new day's missions if needed. True if they were replaced."""
    block = save.data.setdefault("missions", {"date": "", "list": []})
    today = save.today_iso()
    entries = block.get("list")
    stale = (block.get("date") != today
             or not isinstance(entries, list)
             or not entries
             or any(not isinstance(e, dict) or e.get("id") not in TEMPLATES_BY_ID
                    for e in entries))
    if stale:
        block["date"] = today
        block["list"] = _roll(today)
        save.mark_dirty()
        return True
    return False


def active(save) -> List[dict]:
    """Today's missions as display-ready dicts."""
    ensure_today(save)
    out: List[dict] = []
    for entry in save.data["missions"]["list"]:
        template = TEMPLATES_BY_ID.get(entry.get("id"))
        if not template:
            continue
        progress = int(entry.get("progress", 0))
        target = int(template["target"])
        out.append({
            "id": template["id"],
            "text": describe(template),
            "progress": min(progress, target),
            "target": target,
            "reward": int(template["reward"]),
            "done": progress >= target,
            "claimed": bool(entry.get("claimed", False)),
            "fraction": 0.0 if target <= 0 else min(1.0, progress / target),
        })
    return out


# --------------------------------------------------------------------------
# Progress
# --------------------------------------------------------------------------


def _bump(save, key: str, amount: int, mode_filter: Optional[str] = None) -> None:
    """Add to (or raise) the progress of every mission tracking ``key``."""
    if amount <= 0:
        return
    changed = False
    for entry in save.data["missions"]["list"]:
        template = TEMPLATES_BY_ID.get(entry.get("id"))
        if not template or template["key"] != key:
            continue
        if mode_filter and template["mode"] != mode_filter:
            continue
        if entry.get("claimed"):
            continue
        current = int(entry.get("progress", 0))
        if template["mode"] == "best":
            new = max(current, amount)
        else:
            new = current + amount
        if new != current:
            entry["progress"] = new
            changed = True
    if changed:
        save.mark_dirty()


def record_run(save, result: Dict[str, object]) -> None:
    """Fold one finished run into today's missions."""
    ensure_today(save)
    completed = bool(result.get("completed"))
    stars = int(result.get("stars", 0) or 0)

    counters = {
        "coins": int(result.get("coins", 0) or 0),
        "distance_m": int(result.get("distance_m", 0) or 0),
        "dodges": int(result.get("dodges", 0) or 0),
        "jumps": int(result.get("jumps", 0) or 0),
        "slides": int(result.get("slides", 0) or 0),
        "powerups": int(result.get("powerups", 0) or 0),
        "best_combo": int(result.get("best_combo", 1) or 1),
        "completed": 1 if completed else 0,
        "stars": stars,
        "_three_star": 1 if stars >= 3 else 0,
    }
    for key, value in counters.items():
        _bump(save, key, value)


def record_spend(save, amount: int) -> None:
    """Shop purchases feed the 'spend DOWN' mission."""
    ensure_today(save)
    _bump(save, "_spend", int(amount))


# --------------------------------------------------------------------------
# Claiming
# --------------------------------------------------------------------------


def claim(save, wallet, mission_id: str) -> Optional[int]:
    """Pay out one finished mission. Returns the reward, or None."""
    ensure_today(save)
    template = TEMPLATES_BY_ID.get(mission_id)
    if not template:
        return None
    for entry in save.data["missions"]["list"]:
        if entry.get("id") != mission_id:
            continue
        if entry.get("claimed"):
            return None
        if int(entry.get("progress", 0)) < int(template["target"]):
            return None
        entry["claimed"] = True
        reward = int(template["reward"])
        wallet.add(reward, "mission")
        save.mark_dirty()
        return reward
    return None


def claimable_count(save) -> int:
    return sum(1 for m in active(save) if m["done"] and not m["claimed"])
