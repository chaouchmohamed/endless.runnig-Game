"""
main.py - Entry point and state machine for BLOCK ADVENTURE.

Run it with:

    python game/main.py

Python puts the script's own directory on ``sys.path``, which is why every module
here imports its siblings flatly.

``Game`` owns the window, the clock, the save, the wallet, audio, the shared
particle system and the twelve screens. PLAYING is the only state that is not a
Screen - it is a ``run.RunSession`` - and everything that happens when a run ends
is funnelled through ``_finish_run`` so scoring, stats, missions, achievements and
unlocks can never disagree about what happened.

``--selftest`` boots the whole game headless, steps every state, plays a scripted
run and exits. It is how the game is verified on a machine with no display.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from typing import Dict, Optional

import pygame

import achievements
import audio as audio_mod
import missions
import particles as particles_mod
import run as run_mod
import screens as screens_mod
import shop as shop_mod
import ui
import voxel
import world as world_mod
from currency import Wallet
from save_system import SaveManager
from settings import (
    FPS,
    GAME_TITLE,
    HEIGHT,
    MAX_DT,
    MAX_LEVEL,
    State,
    TRANSITION_TIME,
    UI_BAD,
    UI_BG,
    UI_GOLD,
    VSYNC,
    WIDTH,
)


class Game:
    """The whole application."""

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        pygame.init()
        try:
            pygame.display.set_caption(GAME_TITLE)
        except pygame.error:
            pass

        flags = 0
        try:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags,
                                                  vsync=1 if VSYNC else 0)
        except (pygame.error, TypeError):
            # Older SDL builds reject the vsync keyword.
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        self.clock = pygame.time.Clock()
        self.running = True

        self.save = SaveManager()
        self.wallet = Wallet(self.save)
        self.audio = audio_mod.Audio(self.save)
        self.fonts = ui.Fonts()
        self.toasts = ui.Toasts()
        self.particles = particles_mod.ParticleSystem(
            bool(self.save.settings.get("particles", True)))
        self.shake = particles_mod.ScreenShake(
            bool(self.save.settings.get("screen_shake", True)))

        self.backdrop = world_mod.MenuBackdrop(
            world_mod.resolve_world(self.save, int(self.save.data.get("level", 1))))
        self.session = run_mod.RunSession(self.save, self.wallet, self.audio,
                                          self.particles, self.shake)

        self.screens: Dict[str, ui.Screen] = {
            State.INTRO: screens_mod.IntroScreen(self),
            State.MENU: screens_mod.MenuScreen(self),
            State.LEVEL_SELECT: screens_mod.LevelSelectScreen(self),
            State.MISSIONS: screens_mod.MissionsScreen(self),
            State.SETTINGS: screens_mod.SettingsScreen(self),
            State.PAUSED: screens_mod.PauseScreen(self),
            State.GAME_OVER: screens_mod.GameOverScreen(self),
            State.LEVEL_COMPLETE: screens_mod.LevelCompleteScreen(self),
            State.SHOP: shop_mod.ShopScreen(self),
            State.CHARACTERS: shop_mod.CharactersScreen(self),
            State.WORLDS: shop_mod.WorldsScreen(self),
        }

        self.state = State.INTRO
        self.prev_state = State.MENU
        self.fade = 0.0                  # 1 -> fully covered, decays to 0
        self.run_hint = 0.0              # controls hint timer on level 1
        self._pending_music: Optional[str] = None

        missions.ensure_today(self.save)
        achievements.refresh(self.save)
        self.audio.prewarm()

        start = State.MENU if self.save.data.get("seen_intro") else State.INTRO
        self.goto(start, fade=False)
        self.save.save()

    # --------------------------------------------------------------- plumbing
    def current_screen(self) -> Optional[ui.Screen]:
        return self.screens.get(self.state)

    def goto(self, state: str, fade: bool = True, **kwargs) -> None:
        """Switch state, entering the new screen."""
        if state == self.state and state != State.PLAYING:
            # Re-entering the same screen still refreshes it.
            screen = self.current_screen()
            if screen:
                screen.enter(**kwargs)
                if screen.track:
                    self.audio.play_music(screen.track)
            return

        old = self.current_screen()
        if old and self.state != State.PLAYING:
            old.leave()
        self.prev_state = self.state
        self.state = state
        if fade:
            self.fade = 1.0

        screen = self.current_screen()
        if screen:
            screen.enter(**kwargs)
            if screen.track:
                self.audio.play_music(screen.track)
        elif state == State.PLAYING:
            track = "final" if self.session.level == MAX_LEVEL else "run"
            self.audio.play_music(track)

    def quit(self) -> None:
        self.running = False

    def apply_settings(self) -> None:
        self.particles.set_enabled(bool(self.save.settings.get("particles", True)))
        self.shake.set_enabled(bool(self.save.settings.get("screen_shake", True)))

    def check_achievements(self) -> None:
        for spec in achievements.refresh(self.save):
            self.toasts.push(f"ACHIEVEMENT  -  {spec['name']}", UI_GOLD, 3.2)
            self.audio.play("unlock")

    def draw_backdrop(self, surf: pygame.Surface) -> None:
        self.backdrop.draw(surf)

    def reset_progress(self) -> None:
        """Wipe the profile back to defaults (guarded by the settings screen)."""
        from save_system import _default_save

        self.save.data = _default_save()
        self.save.mark_dirty()
        self.save.save(force=True)
        self.wallet.display = 0.0
        missions.ensure_today(self.save)
        self.apply_settings()
        self.goto(State.MENU)

    # ------------------------------------------------------------------- runs
    def start_run(self, level: int) -> None:
        level = max(1, min(MAX_LEVEL, int(level)))
        unlocked = int(self.save.data.get("level", 1))
        if level > unlocked:
            self.toasts.push("Level locked", UI_BAD)
            self.audio.play("denied")
            return

        self.session.start(level)
        self.save.bump_stat("runs", 1)
        self.backdrop.set_world(self.session.world_spec)
        self.run_hint = 4.5 if level == 1 else 0.0
        self.toasts.clear()
        self.goto(State.PLAYING)

    def abandon_run(self) -> None:
        """Leave a run without recording a result."""
        self.session.started = False
        self.save.save()
        self.goto(State.MENU)

    def _finish_run(self, outcome: str) -> None:
        """The single place a run's consequences are applied."""
        result = self.session.result()
        save = self.save

        # --- stats ---------------------------------------------------------
        save.bump_stat("total_distance", int(result["distance_m"]))
        save.bump_stat("total_coins", int(result["coins"]))
        save.bump_stat("jumps", int(result["jumps"]))
        save.bump_stat("slides", int(result["slides"]))
        save.bump_stat("obstacles_dodged", int(result["dodges"]))
        save.bump_stat("powerups_collected", int(result["powerups"]))
        save.set_stat_max("best_combo", int(result["best_combo"]))
        # high_score and best_distance are top-level keys, not stats.
        if int(result["score"]) > int(save.data.get("high_score", 0)):
            save.data["high_score"] = int(result["score"])
        if int(result["distance_m"]) > int(save.data.get("best_distance", 0)):
            save.data["best_distance"] = int(result["distance_m"])
        save.mark_dirty()

        first_clear = False
        unlocked_next = 0

        if outcome == "completed":
            level = int(result["level"])
            stars = int(result["stars"])
            first_clear = save.record_level(level, stars, int(result["score"]))
            if first_clear:
                reward = int(result["reward"])
                self.wallet.add(reward, "level_reward")
                if level == MAX_LEVEL:
                    save.data["final_beaten"] = True
                    save.mark_dirty()
            if level < MAX_LEVEL and level >= int(save.data.get("level", 1)):
                save.unlock_level(level + 1)
                unlocked_next = level + 1
        else:
            save.bump_stat("deaths", 1)

        missions.record_run(save, result)
        self.check_achievements()
        save.save(force=True)

        if outcome == "completed":
            self.goto(State.LEVEL_COMPLETE, result=result, first_clear=first_clear,
                      unlocked_next=unlocked_next)
        else:
            self.goto(State.GAME_OVER, result=result)

    # ------------------------------------------------------------------ input
    def _handle_playing_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if key in (pygame.K_ESCAPE, pygame.K_p):
            self.audio.play("click")
            self.goto(State.PAUSED, fade=False)
        elif key in (pygame.K_LEFT, pygame.K_a):
            self.session.handle_action("left")
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.session.handle_action("right")
        elif key in (pygame.K_UP, pygame.K_w, pygame.K_SPACE):
            self.session.handle_action("jump")
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.session.handle_action("slide")

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
                cfg = self.save.settings
                cfg["show_fps"] = not bool(cfg.get("show_fps", False))
                self.save.mark_dirty()
                continue

            if self.state == State.PLAYING:
                self._handle_playing_event(event)
            else:
                screen = self.current_screen()
                if screen:
                    screen.handle_event(event)

    # ----------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        self.wallet.update(dt)
        self.toasts.update(dt)
        if self.fade > 0.0:
            self.fade = max(0.0, self.fade - dt / TRANSITION_TIME)

        if self.state == State.PLAYING:
            self.shake.update(dt)
            self.particles.update(dt)
            if self.run_hint > 0.0:
                self.run_hint = max(0.0, self.run_hint - dt)
            self.save.bump_stat("play_time", dt)
            outcome = self.session.update(dt)
            if outcome:
                self._finish_run(outcome)
        else:
            screen = self.current_screen()
            if screen:
                screen.update(dt)
            # Death and completion screens keep the effects alive behind them.
            if self.state in (State.GAME_OVER, State.LEVEL_COMPLETE, State.PAUSED):
                self.shake.update(dt)

        self.save.autosave()

    # ------------------------------------------------------------------- draw
    def draw(self) -> None:
        surf = self.screen
        surf.fill(UI_BG)

        if self.state == State.PLAYING:
            self.session.draw(surf)
            ui.draw_hud(surf, self.fonts, self.session, self.wallet,
                        bool(self.save.settings.get("show_fps", False)),
                        self.clock.get_fps())
            if self.run_hint > 0.0:
                ui.draw_controls_hint(surf, self.fonts, min(1.0, self.run_hint / 1.2))
        else:
            screen = self.current_screen()
            if screen:
                screen.draw(surf)

        self.toasts.draw(surf, self.fonts)

        if self.fade > 0.0:
            veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((*UI_BG, int(235 * min(1.0, self.fade))))
            surf.blit(veil, (0, 0))

        pygame.display.flip()

    # ------------------------------------------------------------------- loop
    def run(self) -> int:
        while self.running:
            dt = min(MAX_DT, self.clock.tick(FPS) / 1000.0)
            self.handle_events()
            self.update(dt)
            self.draw()
        self.shutdown()
        return 0

    def shutdown(self) -> None:
        self.save.save(force=True)
        self.audio.shutdown()
        pygame.quit()


# --------------------------------------------------------------------------
# Self test
# --------------------------------------------------------------------------


def selftest(levels=(1, 2, 25, 60, 120, 200), seconds: float = 12.0) -> int:
    """Boot headless, visit every state, play scripted runs. Returns an exit code."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    print("booting...")
    game = Game(headless=True)
    dt = 1.0 / 60.0
    problems = []

    # --- every screen renders -------------------------------------------
    for state in (State.INTRO, State.MENU, State.LEVEL_SELECT, State.MISSIONS,
                  State.SETTINGS, State.SHOP, State.CHARACTERS, State.WORLDS):
        try:
            game.goto(state)
            for _ in range(8):
                game.update(dt)
                game.draw()
            print(f"  ok  {state}")
        except Exception:
            problems.append(f"{state}: {traceback.format_exc()}")
            print(f"  FAIL {state}")

    # --- scripted runs ---------------------------------------------------
    # Unlock everything so every level is reachable, then play each one with a
    # simple bot: jump when something jumpable is close, slide when it is a bar.
    game.save.data["level"] = MAX_LEVEL
    for lvl in levels:
        try:
            game.start_run(lvl)
            session = game.session
            steps = int(seconds / dt)
            for i in range(steps):
                _bot(session)
                game.update(dt)
                game.draw()
                if game.state != State.PLAYING:
                    break
            base, scaled = voxel.CACHE.stats()
            print(f"  ok  run L{lvl:3d}  {int(session.distance_m):5d}m  "
                  f"score={session.score:7d}  coins={session.coins:4d}  "
                  f"state={game.state}  cache={base}/{scaled}")
        except Exception:
            problems.append(f"run {lvl}: {traceback.format_exc()}")
            print(f"  FAIL run L{lvl}")

    # --- end-of-run screens ---------------------------------------------
    for state in (State.PAUSED, State.GAME_OVER, State.LEVEL_COMPLETE):
        try:
            game.goto(state, result=game.session.result(), first_clear=True,
                      unlocked_next=2)
            for _ in range(60):
                game.update(dt)
                game.draw()
            print(f"  ok  {state}")
        except Exception:
            problems.append(f"{state}: {traceback.format_exc()}")
            print(f"  FAIL {state}")

    # --- the save survives a round trip ---------------------------------
    try:
        game.save.save(force=True)
        reloaded = SaveManager(game.save.path)
        assert reloaded.data["level"] >= 1
        print(f"  ok  save round-trip ({reloaded.path})")
    except Exception:
        problems.append(f"save: {traceback.format_exc()}")
        print("  FAIL save round-trip")

    game.shutdown()

    if problems:
        print(f"\n{len(problems)} PROBLEM(S):\n")
        for p in problems:
            print(p)
        return 1
    print("\nselftest passed")
    return 0


def _bot(session) -> None:
    """A crude autopilot, just good enough to exercise the systems."""
    if not session.started or session.plan is None:
        return
    field = session.field
    if field is None:
        return
    player = session.player
    for obs in field.active:
        z = obs.z(session.travelled)
        if not (40.0 < z < 300.0):
            continue
        # Only react to things in our lane.
        if abs(obs.x - player.x) > 70.0:
            continue
        action = obs.spec["action"]
        if action == "jump":
            session.handle_action("jump")
        elif action == "slide":
            session.handle_action("slide")
        else:
            session.handle_action("left" if player.lane > 0 else "right")
        return


# --------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=GAME_TITLE)
    parser.add_argument("--selftest", action="store_true",
                        help="run headless verification and exit")
    parser.add_argument("--level", type=int, default=0,
                        help="jump straight into a level")
    parser.add_argument("--seconds", type=float, default=12.0,
                        help="selftest: seconds to play per level")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(seconds=args.seconds)

    try:
        game = Game()
        if args.level:
            game.save.unlock_level(args.level)
            game.start_run(args.level)
        return game.run()
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 0


if __name__ == "__main__":
    sys.exit(main())
