"""Tests for save persistence, the DOWN wallet, missions and achievements.

These are the systems where a bug quietly corrupts a player's profile rather
than crashing, so they are worth testing hard.
"""

from __future__ import annotations

import json

import pytest

import achievements
import missions
import powerups as pu_mod
from save_system import SaveManager, _default_save
from settings import MAX_LEVEL, POWERUP_MAX_LEVEL


# --------------------------------------------------------------------------
# Save file
# --------------------------------------------------------------------------


def test_fresh_save_has_every_default(save):
    for key in _default_save():
        assert key in save.data
    assert save.data["characters_owned"] == ["starter"]
    assert save.data["worlds_owned"] == ["green_valley"]


def test_save_and_reload_round_trip(save):
    save.data["down"] = 4321
    save.data["level"] = 42
    assert save.save(force=True)
    again = SaveManager(save.path)
    assert again.data["down"] == 4321
    assert again.data["level"] == 42


def test_corrupt_file_is_quarantined_not_fatal(tmp_path):
    path = tmp_path / "save.json"
    path.write_text("{ this is not json at all", encoding="utf-8")
    manager = SaveManager(str(path))
    assert manager.data["down"] == 0
    assert (tmp_path / "save.json.corrupt").exists()


def test_partial_save_is_filled_in(tmp_path):
    path = tmp_path / "save.json"
    path.write_text(json.dumps({"down": 99, "stats": {"runs": 5}}), encoding="utf-8")
    manager = SaveManager(str(path))
    assert manager.data["down"] == 99
    assert manager.data["stats"]["runs"] == 5
    assert manager.data["stats"]["jumps"] == 0        # filled from defaults
    assert manager.data["character"] == "starter"


def test_sanitize_clamps_hostile_values(tmp_path):
    path = tmp_path / "save.json"
    path.write_text(json.dumps({
        "down": -500,
        "level": 99999,
        "character": "does_not_exist",
        "world": "nope",
        "characters_owned": "not a list",
        "levels_completed": {"7": {"stars": 99}, "bad": {}, "50000": {}},
        "powerup_levels": {"magnet": 99},
        "settings": {"music_volume": 12.0, "sfx": "yes"},
    }), encoding="utf-8")
    manager = SaveManager(str(path))

    assert manager.data["down"] == 0
    assert manager.data["level"] == MAX_LEVEL
    assert manager.data["character"] == "starter"
    assert manager.data["world"] == "green_valley"
    assert "starter" in manager.data["characters_owned"]
    assert manager.data["levels_completed"]["7"]["stars"] == 3
    assert "bad" not in manager.data["levels_completed"]
    assert "50000" not in manager.data["levels_completed"]
    assert manager.data["powerup_levels"]["magnet"] == POWERUP_MAX_LEVEL
    assert manager.data["settings"]["music_volume"] <= 1.0
    assert manager.data["settings"]["sfx"] is True


def test_record_level_keeps_the_best_result(save):
    assert save.record_level(5, 2, 1000) is True       # first clear
    assert save.record_level(5, 1, 500) is False       # a worse replay
    record = save.level_record(5)
    assert record == {"stars": 2, "score": 1000}
    save.record_level(5, 3, 4000)
    assert save.level_record(5) == {"stars": 3, "score": 4000}
    assert save.stats["levels_cleared"] == 1           # counted once only


def test_unlock_level_never_goes_backwards(save):
    save.unlock_level(30)
    assert save.data["level"] == 30
    save.unlock_level(4)
    assert save.data["level"] == 30
    save.unlock_level(99999)
    assert save.data["level"] == MAX_LEVEL


def test_stat_helpers(save):
    save.bump_stat("jumps", 3)
    save.bump_stat("jumps", 2)
    assert save.stats["jumps"] == 5
    save.set_stat_max("best_combo", 4)
    save.set_stat_max("best_combo", 2)
    assert save.stats["best_combo"] == 4


# --------------------------------------------------------------------------
# Wallet
# --------------------------------------------------------------------------


def test_wallet_add_and_spend(wallet):
    assert wallet.balance == 0
    wallet.add(500, "test")
    assert wallet.balance == 500
    assert wallet.lifetime == 500
    assert wallet.spend(200, "test") is True
    assert wallet.balance == 300
    assert wallet.lifetime == 500        # spending does not reduce lifetime


def test_wallet_refuses_unaffordable_and_negative(wallet):
    wallet.add(100, "test")
    assert wallet.spend(101, "test") is False
    assert wallet.balance == 100
    assert wallet.spend(-50, "test") is False
    assert wallet.balance == 100
    assert wallet.add(-10, "test") == 0
    assert wallet.balance == 100


def test_wallet_display_eases_toward_balance(wallet):
    wallet.add(1000, "test")
    assert wallet.display_int == 0
    for _ in range(200):
        wallet.update(1 / 60.0)
    assert wallet.display_int == 1000


def test_wallet_writes_through_to_save(wallet, save):
    wallet.add(777, "test")
    save.save(force=True)
    assert SaveManager(save.path).data["down"] == 777


# --------------------------------------------------------------------------
# Power-up economics
# --------------------------------------------------------------------------


def test_duration_grows_with_level():
    prev = 0.0
    for lvl in range(1, POWERUP_MAX_LEVEL + 1):
        d = pu_mod.duration_for("magnet", lvl)
        assert d > prev
        prev = d


def test_character_bonus_extends_duration():
    plain = pu_mod.duration_for("shield", 1, "starter")
    guardian = pu_mod.duration_for("shield", 1, "angel")   # +22% shield, +10% pu
    assert guardian > plain


def test_upgrade_cost_rises_then_maxes_out():
    costs = [pu_mod.upgrade_cost(l) for l in range(1, POWERUP_MAX_LEVEL)]
    assert all(c is not None for c in costs)
    assert costs == sorted(costs)
    assert pu_mod.upgrade_cost(POWERUP_MAX_LEVEL) is None


def test_manager_activates_and_expires(save):
    mgr = pu_mod.PowerupManager(save, "starter")
    mgr.reset()
    mgr.activate("magnet")
    assert mgr.active("magnet")
    assert mgr.magnet_range() > 0.0
    total = mgr.duration("magnet")
    expired = mgr.update(total + 0.1)
    assert "magnet" in expired
    assert not mgr.active("magnet")
    assert mgr.magnet_range() == 0.0


def test_shield_absorbs_exactly_one_hit(save):
    mgr = pu_mod.PowerupManager(save, "starter")
    mgr.reset()
    mgr.activate("shield")
    assert mgr.consume_shield(1.0) is True
    assert mgr.invulnerable()
    assert mgr.consume_shield(1.0) is False


def test_start_shield_character_begins_protected(save):
    mgr = pu_mod.PowerupManager(save, "lava_golem")
    mgr.reset()
    assert mgr.shield_ready
    assert mgr.collected == 0        # a freebie must not count as a pickup


def test_speed_multipliers_compose(save):
    mgr = pu_mod.PowerupManager(save, "starter")
    mgr.reset()
    assert mgr.speed_mult() == pytest.approx(1.0)
    mgr.activate("speed_boost")
    boosted = mgr.speed_mult()
    assert boosted > 1.0
    mgr.activate("slow_motion")
    assert mgr.speed_mult() < boosted


# --------------------------------------------------------------------------
# Missions
# --------------------------------------------------------------------------


def test_missions_are_stable_for_the_day(save):
    missions.ensure_today(save)
    first = [m["id"] for m in missions.active(save)]
    missions.ensure_today(save)
    assert [m["id"] for m in missions.active(save)] == first


def test_missions_refresh_on_a_new_day(save):
    missions.ensure_today(save)
    before = [m["id"] for m in missions.active(save)]
    save.data["missions"]["date"] = "1999-01-01"
    assert missions.ensure_today(save) is True
    after = [m["id"] for m in missions.active(save)]
    assert len(after) == len(before) == missions.DAILY_COUNT


def test_missions_are_deterministic_per_date():
    a = missions._roll("2026-08-26")
    b = missions._roll("2026-08-26")
    c = missions._roll("2026-08-27")
    assert [m["id"] for m in a] == [m["id"] for m in b]
    # Different days should not be forced to differ, but they usually will.
    assert isinstance(c, list) and len(c) == missions.DAILY_COUNT


def test_mission_progress_and_single_claim(save, wallet):
    missions.ensure_today(save)
    entry = save.data["missions"]["list"][0]
    template = missions.TEMPLATES_BY_ID[entry["id"]]

    assert missions.claim(save, wallet, entry["id"]) is None    # not done yet
    entry["progress"] = template["target"]

    before = wallet.balance
    reward = missions.claim(save, wallet, entry["id"])
    assert reward == template["reward"]
    assert wallet.balance == before + reward
    assert missions.claim(save, wallet, entry["id"]) is None    # only once


def test_record_run_advances_matching_missions(save):
    missions.ensure_today(save)
    # Force a known mission so the assertion cannot be flaky.
    save.data["missions"]["list"] = [{"id": "coins_total", "progress": 0, "claimed": False}]
    missions.record_run(save, {"coins": 40, "completed": False, "stars": 0})
    missions.record_run(save, {"coins": 35, "completed": False, "stars": 0})
    assert save.data["missions"]["list"][0]["progress"] == 75


def test_best_mode_missions_keep_the_maximum(save):
    missions.ensure_today(save)
    save.data["missions"]["list"] = [{"id": "combo_best", "progress": 0, "claimed": False}]
    missions.record_run(save, {"best_combo": 5})
    missions.record_run(save, {"best_combo": 2})
    assert save.data["missions"]["list"][0]["progress"] == 5


def test_corrupt_mission_list_is_rerolled(save):
    save.data["missions"] = {"date": save.today_iso(),
                            "list": [{"id": "no_such_mission"}]}
    assert missions.ensure_today(save) is True
    assert all(m["id"] in missions.TEMPLATES_BY_ID
               for m in save.data["missions"]["list"])


# --------------------------------------------------------------------------
# Achievements
# --------------------------------------------------------------------------


def test_achievement_unlocks_once(save):
    assert achievements.refresh(save) == []
    save.record_level(1, 3, 900)
    unlocked = [a["id"] for a in achievements.refresh(save)]
    assert "first_adventure" in unlocked
    assert achievements.refresh(save) == []      # not reported twice


def test_achievement_claim_pays_once(save, wallet):
    save.record_level(1, 1, 100)
    achievements.refresh(save)
    before = wallet.balance
    reward = achievements.claim(save, wallet, "first_adventure")
    assert reward == achievements.BY_ID["first_adventure"]["reward"]
    assert wallet.balance == before + reward
    assert achievements.claim(save, wallet, "first_adventure") is None


def test_cannot_claim_an_incomplete_achievement(save, wallet):
    assert achievements.claim(save, wallet, "the_legend") is None
    assert wallet.balance == 0


def test_status_reports_progress_fractions(save):
    save.data["lifetime_down"] = 500
    rows = {a["id"]: a for a in achievements.status(save)}
    pocket = rows["pocket_change"]
    assert pocket["target"] == 1000
    assert pocket["current"] == 500
    assert pocket["fraction"] == pytest.approx(0.5)


def test_star_helpers_count_correctly(save):
    save.record_level(1, 3, 100)
    save.record_level(2, 2, 100)
    save.record_level(3, 3, 100)
    assert achievements.total_stars(save) == 8
    assert achievements.three_star_levels(save) == 2


def test_claim_all_collects_everything_available(save, wallet):
    save.record_level(1, 1, 10)
    save.record_level(10, 1, 10)
    achievements.refresh(save)
    total = achievements.claim_all(save, wallet)
    assert total > 0
    assert achievements.claimable_count(save) == 0
