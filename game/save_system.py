"""
save_system.py - Durable JSON persistence for BLOCK ADVENTURE.

The save file is written atomically (temp file + os.replace) so a crash or a
kill mid-write can never leave a truncated save behind. Every key has a default
so an older or hand-edited save is repaired instead of rejected.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from datetime import date
from typing import Any, Dict

from settings import DATA_DIR, SAVE_PATH, SAVE_VERSION


def _default_save() -> Dict[str, Any]:
    return {
        "version": SAVE_VERSION,
        "created": time.time(),
        "down": 0,
        "lifetime_down": 0,
        "level": 1,                    # highest unlocked level
        "levels_completed": {},        # "17": {"stars": 3, "score": 12045}
        "high_score": 0,
        "best_distance": 0,
        "characters_owned": ["starter"],
        "character": "starter",
        "worlds_owned": ["green_valley"],
        "world": "green_valley",
        "world_auto": True,            # follow each level's themed world when owned
        "powerup_levels": {},          # {"magnet": 2, ...}
        "missions": {
            "date": "",
            "list": [],                # [{"id":..., "progress":..., "claimed":False}]
        },
        "achievements": {},            # {"first_adventure": {"done":True,"claimed":True}}
        "stats": {
            "runs": 0,
            "total_distance": 0,
            "total_coins": 0,
            "jumps": 0,
            "slides": 0,
            "obstacles_dodged": 0,
            "powerups_collected": 0,
            "deaths": 0,
            "levels_cleared": 0,
            "play_time": 0.0,
            "best_combo": 0,
        },
        "settings": {
            "music": True,
            "sfx": True,
            "music_volume": 0.55,
            "sfx_volume": 0.75,
            "show_fps": False,
            "particles": True,
            "screen_shake": True,
        },
        "seen_intro": False,
        "final_beaten": False,
    }


def _deep_fill(target: Dict[str, Any], defaults: Dict[str, Any]) -> None:
    """Recursively add any missing default keys into ``target``."""
    for key, value in defaults.items():
        if key not in target:
            target[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_fill(target[key], value)


class SaveManager:
    """Loads, repairs, holds and persists the player's profile."""

    AUTOSAVE_INTERVAL = 6.0

    def __init__(self, path: str = SAVE_PATH) -> None:
        self.path = path
        self.data: Dict[str, Any] = _default_save()
        self._dirty = False
        self._last_save = 0.0
        self.load()

    # ---------------------------------------------------------------- load
    def load(self) -> None:
        raw: Dict[str, Any] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                raw = loaded
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # Corrupt save: keep a copy for forensics, then start fresh.
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass

        self.data = raw
        _deep_fill(self.data, _default_save())
        self._migrate()
        self._sanitize()
        self._dirty = True          # make sure a repaired file is written back

    def _migrate(self) -> None:
        version = self.data.get("version", 0)
        if not isinstance(version, int):
            version = 0
        # Future schema changes hook in here; v1 is the initial format.
        self.data["version"] = SAVE_VERSION

    def _sanitize(self) -> None:
        """Force types and clamp ranges so bad data can never crash the game."""
        from settings import MAX_LEVEL, POWERUP_MAX_LEVEL

        def as_int(key: str, low: int, high: int, default: int) -> None:
            try:
                self.data[key] = max(low, min(high, int(self.data.get(key, default))))
            except (TypeError, ValueError):
                self.data[key] = default

        as_int("down", 0, 10 ** 12, 0)
        as_int("lifetime_down", 0, 10 ** 12, 0)
        as_int("level", 1, MAX_LEVEL, 1)
        as_int("high_score", 0, 10 ** 12, 0)
        as_int("best_distance", 0, 10 ** 9, 0)

        for key in ("characters_owned", "worlds_owned"):
            value = self.data.get(key)
            if not isinstance(value, list):
                value = []
            self.data[key] = [str(v) for v in value if isinstance(v, (str, int))]
        if "starter" not in self.data["characters_owned"]:
            self.data["characters_owned"].append("starter")
        if "green_valley" not in self.data["worlds_owned"]:
            self.data["worlds_owned"].append("green_valley")

        if self.data.get("character") not in self.data["characters_owned"]:
            self.data["character"] = "starter"
        if self.data.get("world") not in self.data["worlds_owned"]:
            self.data["world"] = "green_valley"

        completed = self.data.get("levels_completed")
        if not isinstance(completed, dict):
            completed = {}
        clean: Dict[str, Any] = {}
        for key, value in completed.items():
            try:
                lvl = int(key)
            except (TypeError, ValueError):
                continue
            if not 1 <= lvl <= MAX_LEVEL:
                continue
            if not isinstance(value, dict):
                value = {}
            stars = value.get("stars", 1)
            score = value.get("score", 0)
            try:
                stars = max(0, min(3, int(stars)))
            except (TypeError, ValueError):
                stars = 1
            try:
                score = max(0, int(score))
            except (TypeError, ValueError):
                score = 0
            clean[str(lvl)] = {"stars": stars, "score": score}
        self.data["levels_completed"] = clean

        pu = self.data.get("powerup_levels")
        if not isinstance(pu, dict):
            pu = {}
        clean_pu: Dict[str, int] = {}
        for key, value in pu.items():
            try:
                clean_pu[str(key)] = max(1, min(POWERUP_MAX_LEVEL, int(value)))
            except (TypeError, ValueError):
                continue
        self.data["powerup_levels"] = clean_pu

        stats = self.data.get("stats", {})
        if not isinstance(stats, dict):
            self.data["stats"] = _default_save()["stats"]
        else:
            for key, default in _default_save()["stats"].items():
                try:
                    stats[key] = type(default)(stats.get(key, default))
                except (TypeError, ValueError):
                    stats[key] = default

        cfg = self.data.get("settings", {})
        if not isinstance(cfg, dict):
            self.data["settings"] = _default_save()["settings"]
        else:
            for key in ("music", "sfx", "show_fps", "particles", "screen_shake"):
                cfg[key] = bool(cfg.get(key, True))
            for key in ("music_volume", "sfx_volume"):
                try:
                    cfg[key] = max(0.0, min(1.0, float(cfg.get(key, 0.6))))
                except (TypeError, ValueError):
                    cfg[key] = 0.6

    # ---------------------------------------------------------------- save
    def mark_dirty(self) -> None:
        self._dirty = True

    def save(self, force: bool = False) -> bool:
        """Write to disk. Returns True when a write actually happened."""
        if not force and not self._dirty:
            return False
        try:
            os.makedirs(os.path.dirname(self.path) or DATA_DIR, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                prefix=".save-", suffix=".tmp", dir=os.path.dirname(self.path) or DATA_DIR
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, indent=2, sort_keys=True)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError:
            return False
        self._dirty = False
        self._last_save = time.time()
        return True

    def autosave(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if self._dirty and now - self._last_save >= self.AUTOSAVE_INTERVAL:
            return self.save()
        return False

    # ------------------------------------------------------------ helpers
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self.data.get(key) != value:
            self.data[key] = value
            self._dirty = True

    @property
    def settings(self) -> Dict[str, Any]:
        return self.data["settings"]

    @property
    def stats(self) -> Dict[str, Any]:
        return self.data["stats"]

    def bump_stat(self, key: str, amount: float = 1) -> None:
        stats = self.data["stats"]
        current = stats.get(key, 0)
        stats[key] = current + amount
        self._dirty = True

    def set_stat_max(self, key: str, value: float) -> None:
        stats = self.data["stats"]
        if value > stats.get(key, 0):
            stats[key] = value
            self._dirty = True

    # ------------------------------------------------------------ profile
    def owns_character(self, cid: str) -> bool:
        return cid in self.data["characters_owned"]

    def owns_world(self, wid: str) -> bool:
        return wid in self.data["worlds_owned"]

    def add_character(self, cid: str) -> None:
        if cid not in self.data["characters_owned"]:
            self.data["characters_owned"].append(cid)
            self._dirty = True

    def add_world(self, wid: str) -> None:
        if wid not in self.data["worlds_owned"]:
            self.data["worlds_owned"].append(wid)
            self._dirty = True

    def powerup_level(self, pid: str) -> int:
        return int(self.data["powerup_levels"].get(pid, 1))

    def set_powerup_level(self, pid: str, level: int) -> None:
        self.data["powerup_levels"][pid] = int(level)
        self._dirty = True

    def level_record(self, level: int) -> Dict[str, int] | None:
        return self.data["levels_completed"].get(str(int(level)))

    def is_level_complete(self, level: int) -> bool:
        return str(int(level)) in self.data["levels_completed"]

    def record_level(self, level: int, stars: int, score: int) -> bool:
        """Store a level result. Returns True if this was a first clear."""
        key = str(int(level))
        prev = self.data["levels_completed"].get(key)
        first = prev is None
        best_stars = max(int(stars), 0 if first else int(prev.get("stars", 0)))
        best_score = max(int(score), 0 if first else int(prev.get("score", 0)))
        self.data["levels_completed"][key] = {"stars": best_stars, "score": best_score}
        if first:
            self.bump_stat("levels_cleared", 1)
        self._dirty = True
        return first

    def unlock_level(self, level: int) -> None:
        from settings import MAX_LEVEL

        level = max(1, min(MAX_LEVEL, int(level)))
        if level > int(self.data["level"]):
            self.data["level"] = level
            self._dirty = True

    def today_iso(self) -> str:
        return date.today().isoformat()
