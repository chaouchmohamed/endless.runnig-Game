"""
shop.py - The three places DOWN gets spent.

settings.State declares SHOP, CHARACTERS and WORLDS separately, so they are three
screens rather than tabs:

    ShopScreen        power-up upgrades
    CharactersScreen  the 25-strong roster
    WorldsScreen      the 8 worlds

The two galleries share ``_GalleryScreen``, since "grid of things you can own,
with a detail panel" is the same problem twice. Every purchase goes through
``Wallet.spend`` and the SaveManager helpers - never by writing to save data
directly - so the balance, the save file and the missions ledger stay in step.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import pygame

import achievements
import missions
import player as player_mod
import powerups as pu_mod
import ui
import voxel
import world as world_mod
from currency import format_down
from settings import (
    HEIGHT,
    POWERUP_MAX_LEVEL,
    RARITY_COLOR,
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
# Shared gallery
# --------------------------------------------------------------------------


class _GalleryScreen(ui.Screen):
    """A grid of ownable items with a detail panel beside it."""

    track = "menu"
    title = "GALLERY"
    subtitle = ""
    columns = 6
    cell = (100, 100)
    grid_origin = (600, 130)
    gap = (8, 8)

    def __init__(self, game) -> None:
        super().__init__(game)
        self.items: List[dict] = []
        self.grid = ui.GridSelect(0, self.columns, self.cell, self.grid_origin, self.gap)

    # -------------------------------------------------------- subclass hooks
    def load_items(self) -> List[dict]:
        raise NotImplementedError

    def is_owned(self, item: dict) -> bool:
        raise NotImplementedError

    def is_current(self, item: dict) -> bool:
        raise NotImplementedError

    def buy(self, item: dict) -> bool:
        raise NotImplementedError

    def select(self, item: dict) -> None:
        raise NotImplementedError

    def draw_thumb(self, surf: pygame.Surface, item: dict, rect: pygame.Rect) -> None:
        raise NotImplementedError

    def draw_detail(self, surf: pygame.Surface, item: dict, rect: pygame.Rect) -> None:
        raise NotImplementedError

    # -------------------------------------------------------------- lifecycle
    def enter(self, **kwargs) -> None:
        self.items = self.load_items()
        self.grid = ui.GridSelect(len(self.items), self.columns, self.cell,
                                  self.grid_origin, self.gap)
        # Open on whatever is currently equipped.
        for i, item in enumerate(self.items):
            if self.is_current(item):
                self.grid.index = i
                break

    def current(self) -> Optional[dict]:
        if 0 <= self.grid.index < len(self.items):
            return self.items[self.grid.index]
        return None

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.audio.play("click")
            self.game.goto(State.MENU)
            return

        action = self.grid.handle_event(event)
        if action == "move":
            self.audio.play("move", 0.6)
        elif action == "activate":
            self._activate()

    def _activate(self) -> None:
        item = self.current()
        if item is None:
            return
        if self.is_owned(item):
            if self.is_current(item):
                self.audio.play("click")
            else:
                self.select(item)
                self.audio.play("click")
                self.game.toasts.push(f"{item['name']} equipped", UI_ACCENT)
                self.save.save()
            return

        price = int(item.get("price", 0))
        if not self.wallet.can_afford(price):
            self.audio.play("denied")
            self.game.toasts.push("Not enough DOWN", UI_BAD)
            return
        if self.buy(item):
            self.audio.play("purchase")
            self.game.toasts.push(f"{item['name']} unlocked!", UI_GOOD)
            missions.record_spend(self.save, price)
            self.game.check_achievements()
            self.save.save()

    # ------------------------------------------------------------------- draw
    def draw(self, surf: pygame.Surface) -> None:
        self.game.draw_backdrop(surf)
        ui.dim(surf, 195)
        ui.header(surf, self.fonts, self.title, self.subtitle, self.wallet.display_int)

        item = self.current()
        detail = pygame.Rect(40, 130, 530, HEIGHT - 130 - 66)
        ui.panel(surf, detail, fill=UI_PANEL)
        if item:
            self.draw_detail(surf, item, detail)

        start, end = self.grid.page_range()
        for i in range(start, end):
            it = self.items[i]
            rect = self.grid.rect_for(i)
            focused = i == self.grid.index
            owned = self.is_owned(it)
            rarity = RARITY_COLOR.get(it.get("rarity", "COMMON"), UI_BORDER)

            fill = UI_PANEL_LIGHT if focused else UI_PANEL
            pygame.draw.rect(surf, fill, rect, border_radius=8)
            pygame.draw.rect(surf, UI_ACCENT if focused else rarity, rect,
                             width=3 if focused else 2, border_radius=8)
            self.draw_thumb(surf, it, rect)

            if not owned:
                shade = pygame.Surface(rect.size, pygame.SRCALPHA)
                shade.fill((8, 10, 16, 150))
                surf.blit(shade, rect.topleft)
                lock = voxel.lock_sprite(26)
                surf.blit(lock, (rect.centerx - 13, rect.centery - 13))
            elif self.is_current(it):
                pygame.draw.circle(surf, UI_GOOD, (rect.right - 14, rect.y + 14), 8)
                pygame.draw.circle(surf, (12, 20, 14), (rect.right - 14, rect.y + 14), 8, 2)

        if self.grid.pages > 1:
            ui.text_center(surf, f"PAGE {self.grid.page + 1} / {self.grid.pages}",
                           self.fonts.get("tiny"), (self.grid_origin[0] + 320),
                           HEIGHT - 70, UI_TEXT_DIM, shadow=False)

        ui.footer_hint(surf, self.fonts,
                       "ARROWS / MOUSE select   -   ENTER buy or equip   -   ESC back")


# --------------------------------------------------------------------------
# Characters
# --------------------------------------------------------------------------


class CharactersScreen(_GalleryScreen):
    title = "CHARACTERS"
    subtitle = "Rarity buys looks and a nudge, never a win button."
    columns = 6
    cell = (100, 100)
    grid_origin = (600, 130)

    def load_items(self) -> List[dict]:
        return list(player_mod.CHARACTERS)

    def is_owned(self, item: dict) -> bool:
        return self.save.owns_character(item["id"])

    def is_current(self, item: dict) -> bool:
        return self.save.data.get("character") == item["id"]

    def buy(self, item: dict) -> bool:
        if not self.wallet.spend(int(item["price"]), f"character:{item['id']}"):
            return False
        self.save.add_character(item["id"])
        self.save.data["character"] = item["id"]
        self.save.mark_dirty()
        return True

    def select(self, item: dict) -> None:
        self.save.data["character"] = item["id"]
        self.save.mark_dirty()

    def draw_thumb(self, surf: pygame.Surface, item: dict, rect: pygame.Rect) -> None:
        portrait = voxel.character_portrait(item["spec"], 62)
        surf.blit(portrait, (rect.centerx - portrait.get_width() // 2,
                             rect.centery - portrait.get_height() // 2 - 4))

    def draw_detail(self, surf: pygame.Surface, item: dict, rect: pygame.Rect) -> None:
        fonts = self.fonts
        portrait = voxel.character_portrait(item["spec"], 190)
        surf.blit(portrait, (rect.centerx - portrait.get_width() // 2, rect.y + 20))

        y = rect.y + 20 + portrait.get_height() + 14
        ui.text_center(surf, item["name"], fonts.get("mid", bold=True), rect.centerx, y)
        y += 38
        ui.rarity_badge(surf, item["rarity"], fonts.get("tiny", bold=True),
                        rect.centerx, y, center=True)
        y += 40
        y += ui.text_block(surf, item.get("desc", ""), fonts.get("small"),
                           rect.x + 26, y, rect.w - 52, UI_TEXT_DIM)
        y += 12

        ui.text(surf, "PERKS", fonts.get("tiny", bold=True), rect.x + 26, y, UI_ACCENT,
                shadow=False)
        y += 22
        for line in player_mod.bonus_lines(item["id"]):
            ui.text(surf, f"+ {line}", fonts.get("small"), rect.x + 26, y, UI_GOOD,
                    shadow=False)
            y += 24

        self._draw_action(surf, item, rect)

    def _draw_action(self, surf: pygame.Surface, item: dict, rect: pygame.Rect) -> None:
        fonts = self.fonts
        bar = pygame.Rect(rect.x + 26, rect.bottom - 66, rect.w - 52, 46)
        owned = self.is_owned(item)
        price = int(item["price"])
        if owned and self.is_current(item):
            label, tone = "EQUIPPED", "quiet"
        elif owned:
            label, tone = "EQUIP", "primary"
        elif self.wallet.can_afford(price):
            label, tone = f"BUY  -  {format_down(price)} DOWN", "primary"
        else:
            label, tone = f"NEED {format_down(price - self.wallet.balance)} MORE", "danger"
        button = ui.Button(bar, label, "activate", font_key="body", tone=tone,
                           enabled=not (owned and self.is_current(item)))
        button.draw(surf, fonts, focused=False)


# --------------------------------------------------------------------------
# Worlds
# --------------------------------------------------------------------------


class WorldsScreen(_GalleryScreen):
    title = "WORLDS"
    subtitle = "Each world themes 25 of the 200 levels."
    columns = 2
    cell = (300, 92)
    grid_origin = (620, 130)
    gap = (14, 12)

    def load_items(self) -> List[dict]:
        return list(world_mod.WORLDS)

    def is_owned(self, item: dict) -> bool:
        return self.save.owns_world(item["id"])

    def is_current(self, item: dict) -> bool:
        return self.save.data.get("world") == item["id"]

    def buy(self, item: dict) -> bool:
        if not self.wallet.spend(int(item["price"]), f"world:{item['id']}"):
            return False
        self.save.add_world(item["id"])
        self.save.data["world"] = item["id"]
        self.save.mark_dirty()
        return True

    def select(self, item: dict) -> None:
        self.save.data["world"] = item["id"]
        self.save.mark_dirty()

    def draw_thumb(self, surf: pygame.Surface, item: dict, rect: pygame.Rect) -> None:
        # A tiny slice of the world's own sky and ground as the swatch.
        inner = rect.inflate(-14, -14)
        pygame.draw.rect(surf, item["sky_top"], (inner.x, inner.y, inner.w, inner.h // 2))
        pygame.draw.rect(surf, item["sky_bottom"],
                         (inner.x, inner.y + inner.h // 4, inner.w, inner.h // 4))
        pygame.draw.rect(surf, item["ground"],
                         (inner.x, inner.centery, inner.w, inner.h // 2))
        pygame.draw.polygon(surf, item["road_a"], [
            (inner.centerx - 10, inner.centery), (inner.centerx + 10, inner.centery),
            (inner.centerx + 34, inner.bottom), (inner.centerx - 34, inner.bottom)])
        ui.text(surf, item["name"], self.fonts.get("tiny", bold=True),
                inner.x + 6, inner.y + 4, UI_TEXT)

    def draw_detail(self, surf: pygame.Surface, item: dict, rect: pygame.Rect) -> None:
        fonts = self.fonts
        preview = pygame.Rect(rect.x + 26, rect.y + 22, rect.w - 52, 210)
        pygame.draw.rect(surf, item["sky_top"], preview)
        pygame.draw.rect(surf, item["sky_bottom"],
                         (preview.x, preview.y + preview.h // 3, preview.w, preview.h // 3))
        pygame.draw.rect(surf, item["ground"],
                         (preview.x, preview.centery + 20, preview.w, preview.h // 2 - 20))
        pygame.draw.polygon(surf, item["road_a"], [
            (preview.centerx - 24, preview.centery + 20),
            (preview.centerx + 24, preview.centery + 20),
            (preview.centerx + 130, preview.bottom), (preview.centerx - 130, preview.bottom)])
        if item.get("sun"):
            pygame.draw.circle(surf, item["sun"],
                               (preview.x + int(preview.w * 0.74), preview.y + 46), 22)
        pygame.draw.rect(surf, UI_BORDER, preview, width=2)

        y = preview.bottom + 16
        ui.text_center(surf, item["name"], fonts.get("mid", bold=True), rect.centerx, y)
        y += 38
        ui.rarity_badge(surf, item["rarity"], fonts.get("tiny", bold=True),
                        rect.centerx, y, center=True)
        y += 40
        y += ui.text_block(surf, item.get("desc", ""), fonts.get("small"),
                           rect.x + 26, y, rect.w - 52, UI_TEXT_DIM)
        y += 10
        first = world_mod.first_level_of(item["id"])
        ui.text(surf, f"Themes levels {first}-{first + world_mod.LEVELS_PER_WORLD - 1}",
                fonts.get("small"), rect.x + 26, y, UI_ACCENT, shadow=False)

        bar = pygame.Rect(rect.x + 26, rect.bottom - 66, rect.w - 52, 46)
        owned = self.is_owned(item)
        price = int(item["price"])
        if owned and self.is_current(item):
            label, tone, enabled = "SELECTED", "quiet", False
        elif owned:
            label, tone, enabled = "SELECT", "primary", True
        elif self.wallet.can_afford(price):
            label, tone, enabled = f"BUY  -  {format_down(price)} DOWN", "primary", True
        else:
            label, tone, enabled = (f"NEED {format_down(price - self.wallet.balance)} MORE",
                                    "danger", True)
        ui.Button(bar, label, "activate", font_key="body", tone=tone,
                  enabled=enabled).draw(surf, fonts, focused=False)


# --------------------------------------------------------------------------
# Power-up upgrades
# --------------------------------------------------------------------------


class ShopScreen(ui.Screen):
    """Spend DOWN on longer power-up durations."""

    track = "menu"
    ROW_H = 78

    def __init__(self, game) -> None:
        super().__init__(game)
        self.kinds: List[str] = list(pu_mod.KINDS)
        self.grid = ui.GridSelect(len(self.kinds), 1, (WIDTH - 160, self.ROW_H),
                                  (80, 132), (0, 8))

    def enter(self, **kwargs) -> None:
        self.grid.clamp()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.audio.play("click")
            self.game.goto(State.MENU)
            return
        action = self.grid.handle_event(event)
        if action == "move":
            self.audio.play("move", 0.6)
        elif action == "activate":
            self._upgrade()

    def _upgrade(self) -> None:
        kind = self.kinds[self.grid.index]
        current = self.save.powerup_level(kind)
        cost = pu_mod.upgrade_cost(current)
        if cost is None:
            self.audio.play("denied")
            self.game.toasts.push(f"{pu_mod.display_name(kind)} is maxed", UI_TEXT_DIM)
            return
        if not self.wallet.can_afford(cost):
            self.audio.play("denied")
            self.game.toasts.push("Not enough DOWN", UI_BAD)
            return
        if not self.wallet.spend(cost, f"upgrade:{kind}"):
            return
        self.save.set_powerup_level(kind, current + 1)
        self.audio.play("purchase")
        self.game.toasts.push(
            f"{pu_mod.display_name(kind)} -> level {current + 1}", UI_GOOD)
        missions.record_spend(self.save, cost)
        self.game.check_achievements()
        self.save.save()

    def draw(self, surf: pygame.Surface) -> None:
        self.game.draw_backdrop(surf)
        ui.dim(surf, 195)
        ui.header(surf, self.fonts, "POWER-UP SHOP",
                  "Upgrades make every power-up last longer.", self.wallet.display_int)

        fonts = self.fonts
        for i, kind in enumerate(self.kinds):
            rect = self.grid.rect_for(i)
            focused = i == self.grid.index
            level = self.save.powerup_level(kind)
            maxed = level >= POWERUP_MAX_LEVEL
            cost = pu_mod.upgrade_cost(level)
            color = voxel.POWERUP_COLORS.get(kind, UI_ACCENT)

            pygame.draw.rect(surf, UI_PANEL_LIGHT if focused else UI_PANEL, rect,
                             border_radius=9)
            pygame.draw.rect(surf, UI_ACCENT if focused else UI_BORDER, rect,
                             width=3 if focused else 2, border_radius=9)

            surf.blit(voxel.powerup_icon(kind, 52), (rect.x + 14, rect.centery - 26))

            ui.text(surf, pu_mod.display_name(kind), fonts.get("body", bold=True),
                    rect.x + 84, rect.y + 12, UI_TEXT)
            ui.text(surf, pu_mod.description(kind), fonts.get("tiny"),
                    rect.x + 84, rect.y + 42, UI_TEXT_DIM, shadow=False)

            # Level pips.
            for p in range(POWERUP_MAX_LEVEL):
                px = rect.x + 84 + p * 20
                py = rect.bottom - 20
                filled = p < level
                pygame.draw.rect(surf, color if filled else UI_BORDER,
                                 (px, py, 15, 8), border_radius=3)

            duration = pu_mod.duration_for(kind, level, self.save.data.get("character", "starter"))
            ui.text(surf, f"{duration:.1f}s", fonts.get("mid", bold=True),
                    rect.x + 640, rect.centery - 16, color)
            ui.text(surf, f"LEVEL {level} / {POWERUP_MAX_LEVEL}", fonts.get("tiny"),
                    rect.x + 640, rect.centery + 14, UI_TEXT_DIM, shadow=False)

            btn = pygame.Rect(rect.right - 250, rect.centery - 22, 230, 44)
            if maxed:
                label, tone, enabled = "MAXED", "quiet", False
            elif self.wallet.can_afford(cost or 0):
                label, tone, enabled = f"UPGRADE  {format_down(cost or 0)}", "primary", True
            else:
                label, tone, enabled = f"{format_down(cost or 0)} DOWN", "danger", True
            ui.Button(btn, label, "up", font_key="small", tone=tone,
                      enabled=enabled).draw(surf, fonts, focused=False)

        ui.footer_hint(surf, self.fonts,
                       "UP / DOWN select   -   ENTER upgrade   -   ESC back")
