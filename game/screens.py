"""
screens.py - Every screen that is not a purchase gallery.

    IntroScreen          the title card (honours ``seen_intro``)
    MenuScreen           the hub
    LevelSelectScreen    all 200 levels, paged, with stars
    MissionsScreen       daily missions + achievements, two tabs
    SettingsScreen       audio, visuals, and a guarded save wipe
    PauseScreen          drawn over the frozen run
    GameOverScreen       retry / level select / menu
    LevelCompleteScreen  star reveal, reward, next level

Screens never touch each other; they ask ``game.goto()`` for the next state.
Shop, Characters and Worlds live in shop.py.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pygame

import achievements
import level as level_mod
import missions
import player as player_mod
import ui
import voxel
import world as world_mod
from currency import format_down
from settings import (
    FINAL_LEVEL,
    GAME_TAGLINE,
    GAME_TITLE,
    HEIGHT,
    MAX_LEVEL,
    State,
    UI_ACCENT,
    UI_BAD,
    UI_BORDER,
    UI_GOLD,
    UI_GOOD,
    UI_PANEL,
    UI_PANEL_LIGHT,
    UI_TEXT,
    UI_TEXT_DIM,
    WIDTH,
)


# --------------------------------------------------------------------------
# Intro
# --------------------------------------------------------------------------


class IntroScreen(ui.Screen):
    """Title card. Any key skips; it self-advances after a few seconds."""

    track = "menu"
    LENGTH = 4.2

    def __init__(self, game) -> None:
        super().__init__(game)
        self.t = 0.0

    def enter(self, **kwargs) -> None:
        self.t = 0.0
        self.save.data["seen_intro"] = True
        self.save.mark_dirty()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self.audio.play("click")
            self.game.goto(State.MENU)

    def update(self, dt: float) -> None:
        self.t += dt
        self.game.backdrop.update(dt)
        if self.t >= self.LENGTH:
            self.game.goto(State.MENU)

    def draw(self, surf: pygame.Surface) -> None:
        self.game.draw_backdrop(surf)
        ui.dim(surf, 120)
        fonts = self.fonts

        # Title drops in, then the tagline fades up under it.
        drop = min(1.0, self.t / 0.85)
        ease = 1.0 - (1.0 - drop) ** 3
        y = -80 + ease * (HEIGHT * 0.30 + 80)
        ui.text_center(surf, GAME_TITLE, fonts.get("title", bold=True), WIDTH // 2, y,
                       UI_GOLD)

        if self.t > 0.9:
            fade = min(1.0, (self.t - 0.9) / 0.7)
            img = fonts.get("mid", bold=True).render(GAME_TAGLINE, True, UI_TEXT)
            img.set_alpha(int(255 * fade))
            surf.blit(img, (WIDTH // 2 - img.get_width() // 2, HEIGHT * 0.30 + 78))

        if self.t > 1.9:
            trophy = voxel.trophy_sprite(120)
            surf.blit(trophy, (WIDTH // 2 - trophy.get_width() // 2, HEIGHT * 0.46))

        if self.t > 2.4:
            pulse = 0.55 + 0.45 * math.sin(self.t * 3.4)
            img = fonts.get("body").render("press any key", True, UI_TEXT_DIM)
            img.set_alpha(int(255 * pulse))
            surf.blit(img, (WIDTH // 2 - img.get_width() // 2, HEIGHT - 96))


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------


class MenuScreen(ui.Screen):
    """The hub. Play resumes at the highest unlocked level."""

    track = "menu"

    def __init__(self, game) -> None:
        super().__init__(game)
        self.buttons = ui.ButtonList()

    def enter(self, **kwargs) -> None:
        self._build()

    def _build(self) -> None:
        level = int(self.save.data.get("level", 1))
        claimable = missions.claimable_count(self.save) + achievements.claimable_count(self.save)
        x, w, h, gap = 74, 340, 58, 12
        y = 226
        specs = [
            (f"PLAY  -  LEVEL {level}", "play", "primary", ""),
            ("LEVEL SELECT", "levels", "normal", f"{self._stars()} stars earned"),
            ("CHARACTERS", "characters", "normal",
             f"{len(self.save.data['characters_owned'])} owned"),
            ("WORLDS", "worlds", "normal", f"{len(self.save.data['worlds_owned'])} owned"),
            ("POWER-UP SHOP", "shop", "normal", ""),
            ("MISSIONS", "missions", "normal",
             f"{claimable} reward(s) ready" if claimable else ""),
            ("SETTINGS", "settings", "quiet", ""),
            ("QUIT", "quit", "quiet", ""),
        ]
        buttons: List[ui.Button] = []
        for label, action, tone, note in specs:
            buttons.append(ui.Button((x, y, w, h), label, action, font_key="body",
                                     tone=tone, note=note))
            y += h + gap
        self.buttons.set(buttons)

    def _stars(self) -> int:
        return achievements.total_stars(self.save)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.game.quit()
            return
        action = self.buttons.handle_event(event)
        if action == "@move":
            self.audio.play("move", 0.6)
            return
        if not action:
            return
        self.audio.play("click")
        if action == "play":
            self.game.start_run(int(self.save.data.get("level", 1)))
        elif action == "levels":
            self.game.goto(State.LEVEL_SELECT)
        elif action == "characters":
            self.game.goto(State.CHARACTERS)
        elif action == "worlds":
            self.game.goto(State.WORLDS)
        elif action == "shop":
            self.game.goto(State.SHOP)
        elif action == "missions":
            self.game.goto(State.MISSIONS)
        elif action == "settings":
            self.game.goto(State.SETTINGS)
        elif action == "quit":
            self.game.quit()

    def update(self, dt: float) -> None:
        self.game.backdrop.update(dt)

    def draw(self, surf: pygame.Surface) -> None:
        self.game.draw_backdrop(surf)
        ui.dim(surf, 150)
        fonts = self.fonts

        ui.text(surf, GAME_TITLE, fonts.get("title", bold=True), 70, 62, UI_GOLD)
        ui.text(surf, GAME_TAGLINE, fonts.get("small", bold=True), 76, 150, UI_ACCENT,
                shadow=False)
        ui.coin_pill(surf, self.wallet.display_int, fonts.get("mid", bold=True),
                     WIDTH - 40, 40)

        self.buttons.draw(surf, fonts)
        self._draw_profile(surf)

    def _draw_profile(self, surf: pygame.Surface) -> None:
        fonts = self.fonts
        card = pygame.Rect(WIDTH - 470, 130, 430, HEIGHT - 130 - 60)
        ui.panel(surf, card, fill=UI_PANEL)

        cid = self.save.data.get("character", "starter")
        spec = player_mod.get_character(cid)
        portrait = voxel.character_portrait(spec["spec"], 170)
        surf.blit(portrait, (card.centerx - portrait.get_width() // 2, card.y + 20))

        y = card.y + 20 + portrait.get_height() + 10
        ui.text_center(surf, spec["name"], fonts.get("mid", bold=True), card.centerx, y)
        y += 36
        ui.rarity_badge(surf, spec["rarity"], fonts.get("tiny", bold=True),
                        card.centerx, y, center=True)
        y += 44

        wspec = world_mod.resolve_world(self.save, int(self.save.data.get("level", 1)))
        ui.text_center(surf, f"NEXT WORLD:  {wspec['name']}", fonts.get("small", bold=True),
                       card.centerx, y, UI_ACCENT, shadow=False)
        y += 34

        stats = self.save.stats
        rows = [
            ("HIGH SCORE", f"{int(self.save.data.get('high_score', 0)):,}"),
            ("BEST DISTANCE", f"{int(self.save.data.get('best_distance', 0)):,} m"),
            ("LEVELS CLEARED", f"{int(stats.get('levels_cleared', 0))} / {MAX_LEVEL}"),
            ("TOTAL RUNS", f"{int(stats.get('runs', 0)):,}"),
            ("LIFETIME DOWN", format_down(self.save.data.get("lifetime_down", 0))),
        ]
        for label, value in rows:
            ui.text(surf, label, fonts.get("tiny"), card.x + 26, y, UI_TEXT_DIM,
                    shadow=False)
            ui.text(surf, value, fonts.get("small", bold=True), card.right - 26, y - 2,
                    UI_TEXT, right=True, shadow=False)
            y += 26

        if self.save.data.get("final_beaten"):
            trophy = voxel.trophy_sprite(56)
            surf.blit(trophy, (card.centerx - 28, card.bottom - 76))


# --------------------------------------------------------------------------
# Level select
# --------------------------------------------------------------------------


class LevelSelectScreen(ui.Screen):
    """All 200 levels in a paged grid, showing stars and lock state."""

    track = "menu"
    COLUMNS = 10
    ROWS = 5
    CELL = (98, 72)

    def __init__(self, game) -> None:
        super().__init__(game)
        self.grid = ui.GridSelect(MAX_LEVEL, self.COLUMNS, self.CELL, (150, 142),
                                  (14, 10), rows_per_page=self.ROWS)

    def enter(self, **kwargs) -> None:
        start = int(kwargs.get("level", self.save.data.get("level", 1)))
        self.grid.index = max(0, min(MAX_LEVEL - 1, start - 1))

    def _unlocked(self, level: int) -> bool:
        return level <= int(self.save.data.get("level", 1))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.audio.play("click")
            self.game.goto(State.MENU)
            return
        action = self.grid.handle_event(event)
        if action == "move":
            self.audio.play("move", 0.6)
        elif action == "activate":
            level = self.grid.index + 1
            if self._unlocked(level):
                self.audio.play("click")
                self.game.start_run(level)
            else:
                self.audio.play("denied")
                self.game.toasts.push("Complete earlier levels first", UI_BAD)

    def draw(self, surf: pygame.Surface) -> None:
        self.game.draw_backdrop(surf)
        ui.dim(surf, 200)
        fonts = self.fonts
        cleared = int(self.save.stats.get("levels_cleared", 0))
        ui.header(surf, fonts, "LEVEL SELECT",
                  f"{cleared} of {MAX_LEVEL} cleared   -   "
                  f"{achievements.total_stars(self.save)} of {MAX_LEVEL * 3} stars",
                  self.wallet.display_int)

        start, end = self.grid.page_range()
        for i in range(start, end):
            level = i + 1
            rect = self.grid.rect_for(i)
            focused = i == self.grid.index
            unlocked = self._unlocked(level)
            record = self.save.level_record(level)
            is_final = level == FINAL_LEVEL

            if not unlocked:
                fill, border = UI_PANEL, UI_BORDER
            elif record:
                fill = voxel.darken(UI_GOOD, 0.72)
                border = UI_GOOD
            else:
                fill, border = UI_PANEL_LIGHT, UI_ACCENT
            if is_final and unlocked:
                fill, border = voxel.darken(UI_GOLD, 0.7), UI_GOLD

            pygame.draw.rect(surf, fill, rect, border_radius=8)
            pygame.draw.rect(surf, UI_ACCENT if focused else border, rect,
                             width=3 if focused else 2, border_radius=8)

            colour = UI_TEXT if unlocked else UI_BORDER
            ui.text_center(surf, str(level), fonts.get("body", bold=True),
                           rect.centerx, rect.y + 16, colour)

            if not unlocked:
                surf.blit(voxel.lock_sprite(18), (rect.centerx - 9, rect.bottom - 26))
            else:
                stars = int(record.get("stars", 0)) if record else 0
                ui.stars_row(surf, rect.centerx, rect.bottom - 22, stars, 3, 15, 3,
                             center=True)

        # Detail strip for the highlighted level.
        level = self.grid.index + 1
        plan_dist = level_mod.distance_for(level)
        wspec = world_mod.world_for_level(level)
        record = self.save.level_record(level)
        strip = pygame.Rect(150, HEIGHT - 152, WIDTH - 300, 78)
        ui.panel(surf, strip, fill=UI_PANEL)
        ui.text(surf, level_mod.level_name(level), fonts.get("body", bold=True),
                strip.x + 20, strip.y + 12, UI_GOLD if level == FINAL_LEVEL else UI_TEXT)
        ui.text(surf, f"{wspec['name']}   -   {int(plan_dist):,} m   -   "
                      f"reward {format_down(level_mod.reward_for(level))} DOWN",
                fonts.get("small"), strip.x + 20, strip.y + 44, UI_TEXT_DIM, shadow=False)
        if record:
            ui.text(surf, f"BEST  {int(record.get('score', 0)):,}",
                    fonts.get("small", bold=True), strip.right - 20, strip.y + 14,
                    UI_GOOD, right=True, shadow=False)
            ui.stars_row(surf, strip.right - 90, strip.y + 44, int(record.get("stars", 0)),
                         3, 20, 4)
        elif not self._unlocked(level):
            ui.text(surf, "LOCKED", fonts.get("small", bold=True), strip.right - 20,
                    strip.y + 26, UI_BORDER, right=True, shadow=False)

        if self.grid.pages > 1:
            ui.text_center(surf, f"PAGE {self.grid.page + 1} / {self.grid.pages}",
                           fonts.get("tiny"), WIDTH // 2, HEIGHT - 66, UI_TEXT_DIM,
                           shadow=False)
        ui.footer_hint(surf, fonts,
                       "ARROWS select   -   PGUP / PGDN page   -   ENTER play   -   ESC back")


# --------------------------------------------------------------------------
# Missions + achievements
# --------------------------------------------------------------------------


class MissionsScreen(ui.Screen):
    """Two tabs: today's three missions, and the achievement list."""

    track = "menu"
    TABS = ("DAILY MISSIONS", "ACHIEVEMENTS")

    def __init__(self, game) -> None:
        super().__init__(game)
        self.tab = 0
        self.rows: List[dict] = []
        self.grid = ui.GridSelect(0, 1, (WIDTH - 160, 92), (80, 168), (0, 8),
                                  rows_per_page=5)

    def enter(self, **kwargs) -> None:
        self._reload()

    def _reload(self) -> None:
        if self.tab == 0:
            self.rows = missions.active(self.save)
            cell = (WIDTH - 160, 104)
            per = 4
        else:
            self.rows = achievements.status(self.save)
            cell = (WIDTH - 160, 86)
            per = 5
        keep = self.grid.index if self.rows else 0
        self.grid = ui.GridSelect(len(self.rows), 1, cell, (80, 176), (0, 8),
                                  rows_per_page=per)
        self.grid.index = min(keep, max(0, len(self.rows) - 1))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                self.audio.play("click")
                self.game.goto(State.MENU)
                return
            if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d,
                             pygame.K_TAB):
                self.tab = 1 - self.tab
                self.audio.play("move", 0.7)
                self._reload()
                return
        action = self.grid.handle_event(event)
        if action == "move":
            self.audio.play("move", 0.6)
        elif action == "activate":
            self._claim()

    def _claim(self) -> None:
        if not self.rows:
            return
        row = self.rows[self.grid.index]
        if not row["done"] or row["claimed"]:
            self.audio.play("denied")
            return
        if self.tab == 0:
            reward = missions.claim(self.save, self.wallet, row["id"])
        else:
            reward = achievements.claim(self.save, self.wallet, row["id"])
        if reward:
            self.audio.play("purchase")
            self.game.toasts.push(f"+{format_down(reward)} DOWN claimed", UI_GOLD)
            self.save.save()
            self._reload()

    def draw(self, surf: pygame.Surface) -> None:
        self.game.draw_backdrop(surf)
        ui.dim(surf, 200)
        fonts = self.fonts
        ready = missions.claimable_count(self.save) + achievements.claimable_count(self.save)
        ui.header(surf, fonts, "MISSIONS",
                  f"{ready} reward(s) ready to claim" if ready else
                  "Missions refresh every day.", self.wallet.display_int)

        # Tabs
        for i, name in enumerate(self.TABS):
            rect = pygame.Rect(80 + i * 300, 122, 280, 42)
            active = i == self.tab
            pygame.draw.rect(surf, UI_PANEL_LIGHT if active else UI_PANEL, rect,
                             border_radius=8)
            pygame.draw.rect(surf, UI_ACCENT if active else UI_BORDER, rect,
                             width=3 if active else 2, border_radius=8)
            ui.text_center(surf, name, fonts.get("small", bold=True), rect.centerx,
                           rect.centery, UI_TEXT if active else UI_TEXT_DIM)

        start, end = self.grid.page_range()
        for i in range(start, end):
            row = self.rows[i]
            rect = self.grid.rect_for(i)
            focused = i == self.grid.index
            done, claimed = row["done"], row["claimed"]

            if claimed:
                fill, border = UI_PANEL, UI_BORDER
            elif done:
                fill, border = voxel.darken(UI_GOOD, 0.7), UI_GOOD
            else:
                fill, border = UI_PANEL, UI_BORDER
            pygame.draw.rect(surf, UI_PANEL_LIGHT if focused else fill, rect,
                             border_radius=9)
            pygame.draw.rect(surf, UI_ACCENT if focused else border, rect,
                             width=3 if focused else 2, border_radius=9)

            title = row.get("text") or row.get("name", "")
            ui.text(surf, title, fonts.get("body", bold=True), rect.x + 22, rect.y + 12,
                    UI_TEXT_DIM if claimed else UI_TEXT)
            if self.tab == 1:
                ui.text(surf, row["desc"], fonts.get("tiny"), rect.x + 22, rect.y + 42,
                        UI_TEXT_DIM, shadow=False)
                bar_y = rect.bottom - 24
            else:
                bar_y = rect.y + 52

            frac = row["fraction"]
            ui.progress_bar(surf, (rect.x + 22, bar_y, 520, 12), frac,
                            fill=UI_GOOD if done else UI_ACCENT)
            ui.text(surf, f"{row['current'] if self.tab == 1 else row['progress']:,}"
                          f" / {row['target']:,}",
                    fonts.get("tiny"), rect.x + 556, bar_y - 3, UI_TEXT_DIM, shadow=False)

            btn = pygame.Rect(rect.right - 250, rect.centery - 22, 230, 44)
            if claimed:
                label, tone, enabled = "CLAIMED", "quiet", False
            elif done:
                label, tone, enabled = f"CLAIM  {format_down(row['reward'])}", "primary", True
            else:
                label, tone, enabled = f"{format_down(row['reward'])} DOWN", "quiet", False
            ui.Button(btn, label, "claim", font_key="small", tone=tone,
                      enabled=enabled).draw(surf, fonts, focused=False)

        if self.grid.pages > 1:
            ui.text_center(surf, f"PAGE {self.grid.page + 1} / {self.grid.pages}",
                           fonts.get("tiny"), WIDTH // 2, HEIGHT - 68, UI_TEXT_DIM,
                           shadow=False)
        ui.footer_hint(surf, fonts,
                       "LEFT / RIGHT switch tab   -   UP / DOWN select   -   "
                       "ENTER claim   -   ESC back")


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


class SettingsScreen(ui.Screen):
    """Audio and visual toggles, plus a two-step save wipe."""

    track = "menu"

    ROWS = (
        ("music", "Music", "toggle"),
        ("music_volume", "Music Volume", "slider"),
        ("sfx", "Sound Effects", "toggle"),
        ("sfx_volume", "SFX Volume", "slider"),
        ("particles", "Particles", "toggle"),
        ("screen_shake", "Screen Shake", "toggle"),
        ("show_fps", "Show FPS", "toggle"),
        ("world_auto", "Auto World Theme", "toggle"),
        ("_reset", "Reset All Progress", "danger"),
    )

    def __init__(self, game) -> None:
        super().__init__(game)
        self.grid = ui.GridSelect(len(self.ROWS), 1, (720, 50), (280, 150), (0, 8))
        self.confirm_reset = False

    def enter(self, **kwargs) -> None:
        self.confirm_reset = False
        self.grid.clamp()

    def _value(self, key: str):
        if key == "world_auto":
            return bool(self.save.data.get("world_auto", True))
        return self.save.settings.get(key)

    def _set(self, key: str, value) -> None:
        if key == "world_auto":
            self.save.data["world_auto"] = bool(value)
        else:
            self.save.settings[key] = value
        self.save.mark_dirty()
        self.audio.apply_settings()
        self.game.apply_settings()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.audio.play("click")
            self.save.save()
            self.game.goto(State.MENU)
            return

        key, label, kind = self.ROWS[self.grid.index]

        # Sliders take left/right themselves, so they must be handled before the
        # grid would consume those keys for navigation.
        if kind == "slider" and event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                step = 0.05 if event.key in (pygame.K_RIGHT, pygame.K_d) else -0.05
                current = float(self._value(key) or 0.0)
                self._set(key, max(0.0, min(1.0, round(current + step, 2))))
                self.audio.play("move", 0.6)
                return

        action = self.grid.handle_event(event)
        if action == "move":
            self.audio.play("move", 0.6)
            self.confirm_reset = False
        elif action == "activate":
            self._activate(key, kind)

    def _activate(self, key: str, kind: str) -> None:
        if kind == "toggle":
            self._set(key, not bool(self._value(key)))
            self.audio.play("click")
        elif kind == "slider":
            # Clicking a slider cycles through quarter steps.
            current = float(self._value(key) or 0.0)
            self._set(key, 0.0 if current >= 0.99 else min(1.0, round(current + 0.25, 2)))
            self.audio.play("click")
        elif kind == "danger":
            if not self.confirm_reset:
                self.confirm_reset = True
                self.audio.play("denied")
                self.game.toasts.push("Press ENTER again to erase everything", UI_BAD, 3.4)
            else:
                self.confirm_reset = False
                self.game.reset_progress()
                self.audio.play("denied")
                self.game.toasts.push("Progress reset", UI_BAD)

    def draw(self, surf: pygame.Surface) -> None:
        self.game.draw_backdrop(surf)
        ui.dim(surf, 205)
        fonts = self.fonts
        ui.header(surf, fonts, "SETTINGS", "Changes save automatically.",
                  self.wallet.display_int)

        for i, (key, label, kind) in enumerate(self.ROWS):
            rect = self.grid.rect_for(i)
            focused = i == self.grid.index
            danger = kind == "danger"

            fill = UI_PANEL_LIGHT if focused else UI_PANEL
            border = (UI_BAD if danger else UI_ACCENT) if focused else UI_BORDER
            pygame.draw.rect(surf, fill, rect, border_radius=9)
            pygame.draw.rect(surf, border, rect, width=3 if focused else 2,
                             border_radius=9)

            ui.text(surf, label, fonts.get("body", bold=True), rect.x + 20,
                    rect.centery - 13, UI_BAD if danger else UI_TEXT)

            if kind == "toggle":
                on = bool(self._value(key))
                pill = pygame.Rect(rect.right - 118, rect.centery - 15, 96, 30)
                pygame.draw.rect(surf, UI_GOOD if on else UI_BORDER, pill,
                                 border_radius=15)
                knob_x = pill.right - 17 if on else pill.x + 17
                pygame.draw.circle(surf, UI_TEXT, (knob_x, pill.centery), 12)
                ui.text(surf, "ON" if on else "OFF", fonts.get("tiny", bold=True),
                        pill.x - 14, rect.centery - 8, UI_GOOD if on else UI_TEXT_DIM,
                        right=True, shadow=False)
            elif kind == "slider":
                value = float(self._value(key) or 0.0)
                bar = pygame.Rect(rect.right - 260, rect.centery - 8, 200, 16)
                ui.progress_bar(surf, bar, value)
                ui.text(surf, f"{int(value * 100)}%", fonts.get("small", bold=True),
                        rect.right - 22, rect.centery - 12, UI_TEXT, right=True,
                        shadow=False)
            elif danger:
                msg = "PRESS ENTER AGAIN" if self.confirm_reset else "ENTER to reset"
                ui.text(surf, msg, fonts.get("small", bold=True), rect.right - 22,
                        rect.centery - 11, UI_BAD if self.confirm_reset else UI_TEXT_DIM,
                        right=True, shadow=False)

        ui.footer_hint(surf, fonts,
                       "UP / DOWN select   -   LEFT / RIGHT adjust   -   "
                       "ENTER toggle   -   ESC back")


# --------------------------------------------------------------------------
# Pause
# --------------------------------------------------------------------------


class PauseScreen(ui.Screen):
    """Drawn over the frozen run, so the road stays visible behind it."""

    def __init__(self, game) -> None:
        super().__init__(game)
        self.buttons = ui.ButtonList()

    def enter(self, **kwargs) -> None:
        cx = WIDTH // 2 - 170
        y = 262
        specs = [("RESUME", "resume", "primary"),
                 ("RESTART LEVEL", "restart", "normal"),
                 ("SETTINGS", "settings", "normal"),
                 ("QUIT TO MENU", "menu", "quiet")]
        buttons = []
        for label, action, tone in specs:
            buttons.append(ui.Button((cx, y, 340, 56), label, action, font_key="body",
                                     tone=tone))
            y += 68
        self.buttons.set(buttons)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_p):
            self.audio.play("click")
            self.game.goto(State.PLAYING)
            return
        action = self.buttons.handle_event(event)
        if action == "@move":
            self.audio.play("move", 0.6)
            return
        if not action:
            return
        self.audio.play("click")
        if action == "resume":
            self.game.goto(State.PLAYING)
        elif action == "restart":
            self.game.start_run(self.game.session.level)
        elif action == "settings":
            self.game.goto(State.SETTINGS)
        elif action == "menu":
            self.game.abandon_run()

    def draw(self, surf: pygame.Surface) -> None:
        session = self.game.session
        if session and session.started:
            session.draw(surf)
            ui.draw_hud(surf, self.fonts, session, self.wallet)
        ui.dim(surf, 190)
        fonts = self.fonts

        card = pygame.Rect(WIDTH // 2 - 260, 130, 520, 500)
        ui.panel(surf, card, fill=UI_PANEL)
        ui.text_center(surf, "PAUSED", fonts.get("huge", bold=True), WIDTH // 2,
                       card.y + 58, UI_ACCENT)
        if session and session.plan:
            ui.text_center(surf, session.plan.name, fonts.get("body", bold=True),
                           WIDTH // 2, card.y + 118, UI_TEXT_DIM)
            ui.progress_bar(surf, (card.x + 60, card.y + 158, card.w - 120, 12),
                            session.progress)
            ui.text_center(surf, f"{int(session.distance_m)} / "
                                 f"{int(session.plan.distance_m)} m   -   "
                                 f"{session.score:,} pts",
                           fonts.get("small"), WIDTH // 2, card.y + 182, UI_TEXT_DIM)
        self.buttons.draw(surf, fonts)


# --------------------------------------------------------------------------
# Game over
# --------------------------------------------------------------------------


class GameOverScreen(ui.Screen):
    """Shown after the death animation finishes."""

    def __init__(self, game) -> None:
        super().__init__(game)
        self.buttons = ui.ButtonList()
        self.result: dict = {}
        self.t = 0.0

    def enter(self, **kwargs) -> None:
        self.result = kwargs.get("result", {}) or {}
        self.t = 0.0
        cx = WIDTH // 2 - 170
        y = 520
        specs = [("RETRY", "retry", "primary"),
                 ("LEVEL SELECT", "levels", "normal"),
                 ("MAIN MENU", "menu", "quiet")]
        buttons = []
        for label, action, tone in specs:
            buttons.append(ui.Button((cx, y, 340, 50), label, action, font_key="body",
                                     tone=tone))
            y += 58
        self.buttons.set(buttons)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.audio.play("click")
            self.game.goto(State.MENU)
            return
        action = self.buttons.handle_event(event)
        if action == "@move":
            self.audio.play("move", 0.6)
            return
        if not action:
            return
        self.audio.play("click")
        if action == "retry":
            self.game.start_run(int(self.result.get("level", 1)))
        elif action == "levels":
            self.game.goto(State.LEVEL_SELECT, level=int(self.result.get("level", 1)))
        elif action == "menu":
            self.game.goto(State.MENU)

    def update(self, dt: float) -> None:
        self.t += dt

    def draw(self, surf: pygame.Surface) -> None:
        session = self.game.session
        if session and session.started:
            session.draw(surf)
        ui.dim(surf, 205)
        fonts = self.fonts
        r = self.result

        card = pygame.Rect(WIDTH // 2 - 300, 74, 600, 424)
        ui.panel(surf, card, fill=UI_PANEL)
        ui.text_center(surf, "RUN OVER", fonts.get("huge", bold=True), WIDTH // 2,
                       card.y + 46, UI_BAD)
        ui.text_center(surf, level_mod.level_name(int(r.get("level", 1))),
                       fonts.get("body", bold=True), WIDTH // 2, card.y + 96, UI_TEXT_DIM)

        # Score counts up, which makes the number feel earned.
        reveal = min(1.0, self.t / 0.8)
        shown = int(int(r.get("score", 0)) * reveal)
        ui.text_center(surf, f"{shown:,}", fonts.get("huge", bold=True), WIDTH // 2,
                       card.y + 130, UI_GOLD)
        ui.text_center(surf, "SCORE", fonts.get("tiny", bold=True), WIDTH // 2,
                       card.y + 192, UI_TEXT_DIM, shadow=False)

        target = max(1, int(r.get("target_m", 1)))
        ui.progress_bar(surf, (card.x + 60, card.y + 222, card.w - 120, 14),
                        float(r.get("progress", 0.0)), fill=UI_BAD)
        ui.text_center(surf, f"{int(r.get('distance_m', 0)):,} / {target:,} m  "
                             f"({float(r.get('progress', 0.0)) * 100:.0f}%)",
                       fonts.get("small"), WIDTH // 2, card.y + 244, UI_TEXT_DIM)

        rows = [
            ("DOWN EARNED", format_down(r.get("down", 0)), UI_GOLD),
            ("COINS", f"{int(r.get('coins', 0)):,}", UI_TEXT),
            ("OBSTACLES DODGED", f"{int(r.get('dodges', 0)):,}", UI_TEXT),
            ("BEST COMBO", f"x{int(r.get('best_combo', 1))}", UI_ACCENT),
        ]
        y = card.y + 282
        for label, value, color in rows:
            ui.text(surf, label, fonts.get("tiny"), card.x + 60, y, UI_TEXT_DIM,
                    shadow=False)
            ui.text(surf, value, fonts.get("small", bold=True), card.right - 60, y - 3,
                    color, right=True, shadow=False)
            y += 27

        self.buttons.draw(surf, fonts)


# --------------------------------------------------------------------------
# Level complete
# --------------------------------------------------------------------------


class LevelCompleteScreen(ui.Screen):
    """Star reveal, then the reward, then what to do next."""

    STAR_AT = (0.55, 1.0, 1.45)

    def __init__(self, game) -> None:
        super().__init__(game)
        self.buttons = ui.ButtonList()
        self.result: dict = {}
        self.t = 0.0
        self._popped = 0
        self.first_clear = False
        self.unlocked_next = 0

    def enter(self, **kwargs) -> None:
        self.result = kwargs.get("result", {}) or {}
        self.first_clear = bool(kwargs.get("first_clear", False))
        self.unlocked_next = int(kwargs.get("unlocked_next", 0))
        self.t = 0.0
        self._popped = 0

        level = int(self.result.get("level", 1))
        has_next = level < MAX_LEVEL
        specs = []
        if has_next:
            specs.append((f"NEXT  -  LEVEL {level + 1}", "next", "primary"))
        specs.append(("REPLAY", "retry", "normal" if has_next else "primary"))
        specs.append(("LEVEL SELECT", "levels", "normal"))
        specs.append(("MAIN MENU", "menu", "quiet"))

        # Two columns, so four options still fit above the bottom of the card.
        buttons = []
        for i, (label, action, tone) in enumerate(specs):
            col, row = i % 2, i // 2
            x = WIDTH // 2 - 290 + col * 300
            y = 552 + row * 54
            buttons.append(ui.Button((x, y, 280, 46), label, action, font_key="small",
                                     tone=tone))
        self.buttons.set(buttons)
        self.buttons.columns = 2

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.audio.play("click")
            self.game.goto(State.MENU)
            return
        action = self.buttons.handle_event(event)
        if action == "@move":
            self.audio.play("move", 0.6)
            return
        if not action:
            return
        self.audio.play("click")
        level = int(self.result.get("level", 1))
        if action == "next":
            self.game.start_run(min(MAX_LEVEL, level + 1))
        elif action == "retry":
            self.game.start_run(level)
        elif action == "levels":
            self.game.goto(State.LEVEL_SELECT, level=level)
        elif action == "menu":
            self.game.goto(State.MENU)

    def update(self, dt: float) -> None:
        self.t += dt
        stars = int(self.result.get("stars", 0))
        # Pop each earned star in turn, with a sound and a burst.
        while self._popped < stars and self.t >= self.STAR_AT[min(2, self._popped)]:
            self._popped += 1
            self.audio.play("star")
            x = WIDTH // 2 + (self._popped - 2) * 90
            self.game.particles.star_pop(x, 176)
        self.game.particles.update(dt)

    def draw(self, surf: pygame.Surface) -> None:
        session = self.game.session
        if session and session.started:
            session.draw(surf)
        ui.dim(surf, 200)
        fonts = self.fonts
        r = self.result
        is_final = int(r.get("level", 1)) == FINAL_LEVEL

        card = pygame.Rect(WIDTH // 2 - 320, 58, 640, 604)
        ui.panel(surf, card, fill=UI_PANEL)

        title = "ADVENTURE COMPLETE!" if is_final else "LEVEL COMPLETE!"
        ui.text_center(surf, title, fonts.get("big", bold=True), WIDTH // 2,
                       card.y + 38, UI_GOLD if is_final else UI_GOOD)
        ui.text_center(surf, level_mod.level_name(int(r.get("level", 1))),
                       fonts.get("body", bold=True), WIDTH // 2, card.y + 82, UI_TEXT_DIM)

        # Stars
        size = 70
        star_y = card.y + 118
        for i in range(3):
            x = WIDTH // 2 + (i - 1) * 90 - size // 2
            filled = i < self._popped
            sprite = voxel.star_sprite(size, filled)
            bump = 0
            if filled and self.t - self.STAR_AT[i] < 0.24:
                bump = int(10 * (1.0 - (self.t - self.STAR_AT[i]) / 0.24))
            surf.blit(sprite, (x, star_y - bump))
        self.game.particles.draw(surf)

        reveal = min(1.0, max(0.0, (self.t - 1.6) / 0.7))
        shown = int(int(r.get("score", 0)) * reveal)
        ui.text_center(surf, f"{shown:,}", fonts.get("huge", bold=True), WIDTH // 2,
                       card.y + 210, UI_TEXT)
        ui.text_center(surf, "SCORE", fonts.get("tiny", bold=True), WIDTH // 2,
                       card.y + 270, UI_TEXT_DIM, shadow=False)

        rows = [
            ("DISTANCE", f"{int(r.get('distance_m', 0)):,} m", UI_TEXT),
            ("COINS", f"{int(r.get('coins', 0)):,}", UI_TEXT),
            ("DOWN EARNED", format_down(r.get("down", 0)), UI_GOLD),
            ("BEST COMBO", f"x{int(r.get('best_combo', 1))}", UI_ACCENT),
        ]
        y = card.y + 302
        for label, value, color in rows:
            ui.text(surf, label, fonts.get("tiny"), card.x + 70, y, UI_TEXT_DIM,
                    shadow=False)
            ui.text(surf, value, fonts.get("small", bold=True), card.right - 70, y - 3,
                    color, right=True, shadow=False)
            y += 26

        if self.first_clear and self.t > 1.4:
            reward = int(r.get("reward", 0))
            chip = pygame.Rect(card.x + 70, y + 6, card.w - 140, 38)
            pygame.draw.rect(surf, voxel.darken(UI_GOLD, 0.72), chip, border_radius=8)
            pygame.draw.rect(surf, UI_GOLD, chip, width=2, border_radius=8)
            ui.text_center(surf, f"FIRST CLEAR BONUS  +{format_down(reward)} DOWN",
                           fonts.get("small", bold=True), chip.centerx, chip.centery,
                           UI_GOLD)
        elif self.unlocked_next and self.t > 1.4:
            ui.text_center(surf, f"LEVEL {self.unlocked_next} UNLOCKED",
                           fonts.get("small", bold=True), WIDTH // 2, y + 16, UI_ACCENT)

        self.buttons.draw(surf, fonts)
