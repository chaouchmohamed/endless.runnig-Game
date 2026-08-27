"""
ui.py - Fonts, widgets and the in-run HUD.

Everything visual outside the road lives here. Two conventions keep the twelve
screens consistent:

* Colour comes only from the ``UI_*`` constants in settings.py, so the whole
  game re-skins from one place.
* ``ButtonList`` owns focus, so every screen supports keyboard *and* mouse
  without each one reimplementing navigation.

Fonts are resolved by trying a list of common system faces and falling back to
pygame's bundled default, so the game renders on a box with no fonts installed.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pygame

import voxel
from currency import format_down
from settings import (
    HEIGHT,
    RARITY_COLOR,
    UI_ACCENT,
    UI_ACCENT_DARK,
    UI_BAD,
    UI_BORDER,
    UI_GOLD,
    UI_GOLD_DARK,
    UI_GOOD,
    UI_PANEL,
    UI_PANEL_LIGHT,
    UI_SHADOW,
    UI_TEXT,
    UI_TEXT_DIM,
    WIDTH,
)

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

FONT_CANDIDATES = (
    "dejavusansmono", "liberationmono", "couriernew",
    "dejavusans", "liberationsans", "freesans", "arial", "helvetica",
)

SIZES = {
    "tiny": 15,
    "small": 19,
    "body": 23,
    "mid": 29,
    "big": 40,
    "huge": 58,
    "title": 78,
}


def _pick_font(bold: bool) -> Optional[str]:
    for name in FONT_CANDIDATES:
        try:
            path = pygame.font.match_font(name, bold=bold)
        except Exception:
            path = None
        if path:
            return path
    return None


class Fonts:
    """Lazily built font set, with a bold variant of every size."""

    def __init__(self) -> None:
        self._regular_path = _pick_font(False)
        self._bold_path = _pick_font(True) or self._regular_path
        self._cache: Dict[Tuple[str, bool], pygame.font.Font] = {}

    def _load(self, key: str, bold: bool) -> pygame.font.Font:
        size = SIZES.get(key, SIZES["body"])
        path = self._bold_path if bold else self._regular_path
        try:
            if path:
                font = pygame.font.Font(path, size)
            else:
                # Bundled default renders small for a given size; nudge it up.
                font = pygame.font.Font(None, int(size * 1.25))
                font.set_bold(bold)
        except Exception:
            font = pygame.font.Font(None, int(size * 1.25))
        return font

    def get(self, key: str = "body", bold: bool = False) -> pygame.font.Font:
        ck = (key, bold)
        font = self._cache.get(ck)
        if font is None:
            font = self._load(key, bold)
            self._cache[ck] = font
        return font

    # Convenience accessors used all over the screens.
    def __call__(self, key: str = "body", bold: bool = False) -> pygame.font.Font:
        return self.get(key, bold)


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------


def text(surf: pygame.Surface, msg: str, font: pygame.font.Font, x: float, y: float,
         color: Sequence[int] = UI_TEXT, shadow: bool = True,
         center: bool = False, right: bool = False) -> pygame.Rect:
    """Draw one line. Returns the rect it occupied."""
    img = font.render(str(msg), True, color)
    rect = img.get_rect()
    if center:
        rect.midtop = (int(x), int(y))
    elif right:
        rect.topright = (int(x), int(y))
    else:
        rect.topleft = (int(x), int(y))
    if shadow:
        sh = font.render(str(msg), True, UI_SHADOW)
        surf.blit(sh, (rect.x + 2, rect.y + 2))
    surf.blit(img, rect)
    return rect


def text_center(surf: pygame.Surface, msg: str, font: pygame.font.Font,
                cx: float, cy: float, color: Sequence[int] = UI_TEXT,
                shadow: bool = True) -> pygame.Rect:
    """Draw centred on both axes."""
    img = font.render(str(msg), True, color)
    rect = img.get_rect(center=(int(cx), int(cy)))
    if shadow:
        surf.blit(font.render(str(msg), True, UI_SHADOW), (rect.x + 2, rect.y + 2))
    surf.blit(img, rect)
    return rect


def wrap(msg: str, font: pygame.font.Font, width: int) -> List[str]:
    """Greedy word wrap to a pixel width."""
    words = str(msg).split()
    if not words:
        return []
    lines: List[str] = []
    line = words[0]
    for word in words[1:]:
        trial = f"{line} {word}"
        if font.size(trial)[0] <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def text_block(surf: pygame.Surface, msg: str, font: pygame.font.Font, x: float, y: float,
               width: int, color: Sequence[int] = UI_TEXT_DIM,
               line_gap: int = 3) -> int:
    """Draw wrapped text. Returns the height used."""
    used = 0
    for line in wrap(msg, font, width):
        text(surf, line, font, x, y + used, color, shadow=False)
        used += font.get_height() + line_gap
    return used


# --------------------------------------------------------------------------
# Panels and bars
# --------------------------------------------------------------------------


def panel(surf: pygame.Surface, rect: Sequence[int], fill: Sequence[int] = UI_PANEL,
          border: Sequence[int] = UI_BORDER, radius: int = 10, width: int = 2,
          shadow: bool = True) -> pygame.Rect:
    r = pygame.Rect(rect)
    if shadow:
        pygame.draw.rect(surf, UI_SHADOW, r.move(0, 4), border_radius=radius)
    pygame.draw.rect(surf, fill, r, border_radius=radius)
    if width > 0:
        pygame.draw.rect(surf, border, r, width=width, border_radius=radius)
    return r


def dim(surf: pygame.Surface, alpha: int = 170) -> None:
    """Darken the whole screen - used behind pause and modal screens."""
    veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    veil.fill((6, 8, 14, max(0, min(255, alpha))))
    surf.blit(veil, (0, 0))


def progress_bar(surf: pygame.Surface, rect: Sequence[int], frac: float,
                 fill: Sequence[int] = UI_ACCENT, back: Sequence[int] = UI_PANEL_LIGHT,
                 radius: int = 6, border: bool = True) -> None:
    r = pygame.Rect(rect)
    frac = max(0.0, min(1.0, frac))
    pygame.draw.rect(surf, back, r, border_radius=radius)
    if frac > 0.0:
        inner = pygame.Rect(r.x, r.y, max(radius * 2, int(r.w * frac)), r.h)
        pygame.draw.rect(surf, fill, inner, border_radius=radius)
        pygame.draw.rect(surf, voxel.lighten(fill, 0.35),
                         (inner.x + 2, inner.y + 2, max(1, inner.w - 4), max(1, inner.h // 3)),
                         border_radius=radius)
    if border:
        pygame.draw.rect(surf, UI_BORDER, r, width=1, border_radius=radius)


def rarity_badge(surf: pygame.Surface, rarity: str, font: pygame.font.Font,
                 x: float, y: float, center: bool = False) -> pygame.Rect:
    color = RARITY_COLOR.get(rarity, UI_TEXT_DIM)
    label = rarity.replace("_", " ")
    tw, th = font.size(label)
    w, h = tw + 18, th + 8
    rect = pygame.Rect(int(x - w / 2) if center else int(x), int(y), w, h)
    pygame.draw.rect(surf, voxel.darken(color, 0.62), rect, border_radius=6)
    pygame.draw.rect(surf, color, rect, width=2, border_radius=6)
    text_center(surf, label, font, rect.centerx, rect.centery, color, shadow=False)
    return rect


def stars_row(surf: pygame.Surface, x: float, y: float, filled: int, total: int = 3,
              size: int = 26, gap: int = 4, center: bool = False) -> None:
    span = total * size + (total - 1) * gap
    left = x - span / 2 if center else x
    for i in range(total):
        surf.blit(voxel.star_sprite(size, i < filled), (int(left + i * (size + gap)), int(y)))


def coin_pill(surf: pygame.Surface, amount: int, font: pygame.font.Font,
              x: float, y: float, right: bool = True) -> pygame.Rect:
    """The DOWN balance chip shown in every menu."""
    label = format_down(amount)
    icon = voxel.coin_icon(24)
    tw = font.size(label)[0]
    w = tw + 24 + 30
    h = max(font.get_height(), 26) + 10
    rect = pygame.Rect(int(x - w) if right else int(x), int(y), w, h)
    pygame.draw.rect(surf, UI_PANEL, rect, border_radius=h // 2)
    pygame.draw.rect(surf, UI_GOLD_DARK, rect, width=2, border_radius=h // 2)
    surf.blit(icon, (rect.x + 9, rect.centery - 12))
    text(surf, label, font, rect.x + 39, rect.centery - font.get_height() // 2, UI_GOLD,
         shadow=False)
    return rect


# --------------------------------------------------------------------------
# Buttons
# --------------------------------------------------------------------------


class Button:
    """One clickable, focusable control."""

    def __init__(self, rect: Sequence[int], label: str, action: str,
                 font_key: str = "mid", enabled: bool = True,
                 tone: str = "normal", note: str = "") -> None:
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.font_key = font_key
        self.enabled = enabled
        self.tone = tone          # normal | primary | danger | quiet
        self.note = note          # small text under the label
        self.hover = False

    def _colors(self, focused: bool) -> Tuple[Sequence[int], Sequence[int], Sequence[int]]:
        if not self.enabled:
            return UI_PANEL, UI_BORDER, UI_TEXT_DIM
        if self.tone == "primary":
            base = UI_ACCENT_DARK if not focused else UI_ACCENT
            return base, voxel.lighten(UI_ACCENT, 0.3), (12, 20, 32) if focused else UI_TEXT
        if self.tone == "danger":
            base = voxel.darken(UI_BAD, 0.45) if not focused else UI_BAD
            return base, voxel.lighten(UI_BAD, 0.3), UI_TEXT
        if self.tone == "quiet":
            base = UI_PANEL if not focused else UI_PANEL_LIGHT
            return base, UI_BORDER, UI_TEXT if focused else UI_TEXT_DIM
        base = UI_PANEL_LIGHT if focused else UI_PANEL
        border = UI_ACCENT if focused else UI_BORDER
        return base, border, UI_TEXT

    def draw(self, surf: pygame.Surface, fonts: Fonts, focused: bool = False) -> None:
        focused = focused or (self.hover and self.enabled)
        fill, border, fg = self._colors(focused)
        r = self.rect
        pygame.draw.rect(surf, UI_SHADOW, r.move(0, 4), border_radius=9)
        pygame.draw.rect(surf, fill, r, border_radius=9)
        pygame.draw.rect(surf, border, r, width=2 if not focused else 3, border_radius=9)

        font = fonts.get(self.font_key, bold=True)
        if self.note:
            text_center(surf, self.label, font, r.centerx, r.centery - 9, fg)
            text_center(surf, self.note, fonts.get("tiny"), r.centerx, r.centery + 14,
                        UI_TEXT_DIM if self.enabled else UI_BORDER, shadow=False)
        else:
            text_center(surf, self.label, font, r.centerx, r.centery, fg)

        if focused and self.enabled:
            # A focus caret, so keyboard users can see where they are.
            pygame.draw.polygon(surf, UI_ACCENT, [
                (r.x - 14, r.centery), (r.x - 4, r.centery - 7), (r.x - 4, r.centery + 7)])


class ButtonList:
    """Keyboard + mouse focus over a set of buttons."""

    def __init__(self, buttons: Optional[List[Button]] = None, columns: int = 1) -> None:
        self.buttons: List[Button] = buttons or []
        self.index = 0
        self.columns = max(1, columns)
        self._settle()

    def set(self, buttons: List[Button], keep_index: bool = False) -> None:
        self.buttons = buttons
        if not keep_index:
            self.index = 0
        self._settle()

    def _settle(self) -> None:
        """Move focus onto an enabled button if the current one is not."""
        if not self.buttons:
            self.index = 0
            return
        self.index = max(0, min(len(self.buttons) - 1, self.index))
        if self.buttons[self.index].enabled:
            return
        for step in range(1, len(self.buttons) + 1):
            j = (self.index + step) % len(self.buttons)
            if self.buttons[j].enabled:
                self.index = j
                return

    def move(self, delta: int) -> bool:
        """Step focus, skipping disabled buttons. True if focus moved."""
        usable = [i for i, b in enumerate(self.buttons) if b.enabled]
        if not usable:
            return False
        if self.index in usable:
            here = usable.index(self.index)
            self.index = usable[(here + delta) % len(usable)]
        else:
            self.index = usable[0]
        return True

    def current(self) -> Optional[Button]:
        if 0 <= self.index < len(self.buttons):
            return self.buttons[self.index]
        return None

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Returns the action of an activated button, or None."""
        if event.type == pygame.MOUSEMOTION:
            for i, b in enumerate(self.buttons):
                b.hover = b.enabled and b.rect.collidepoint(event.pos)
                if b.hover:
                    self.index = i
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for b in self.buttons:
                if b.enabled and b.rect.collidepoint(event.pos):
                    return b.action
            return None

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_DOWN, pygame.K_s, pygame.K_TAB):
                return "@move" if self.move(1) else None
            if event.key in (pygame.K_UP, pygame.K_w):
                return "@move" if self.move(-1) else None
            if event.key in (pygame.K_RIGHT, pygame.K_d) and self.columns > 1:
                return "@move" if self.move(1) else None
            if event.key in (pygame.K_LEFT, pygame.K_a) and self.columns > 1:
                return "@move" if self.move(-1) else None
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                b = self.current()
                if b and b.enabled:
                    return b.action
        return None

    def draw(self, surf: pygame.Surface, fonts: Fonts) -> None:
        for i, b in enumerate(self.buttons):
            b.draw(surf, fonts, focused=(i == self.index))


# --------------------------------------------------------------------------
# Grid selection
# --------------------------------------------------------------------------


class GridSelect:
    """Keyboard + mouse selection over a grid of equal cells.

    The caller owns the drawing; this only tracks which index is selected and
    where each cell is, which is what the character gallery, the world gallery
    and the 200-level picker all needed independently.
    """

    def __init__(self, count: int, columns: int, cell: Tuple[int, int],
                 origin: Tuple[int, int], gap: Tuple[int, int] = (10, 10),
                 rows_per_page: int = 0) -> None:
        self.count = max(0, int(count))
        self.columns = max(1, int(columns))
        self.cell_w, self.cell_h = cell
        self.ox, self.oy = origin
        self.gap_x, self.gap_y = gap
        self.rows_per_page = rows_per_page or 10_000
        self.index = 0

    # ------------------------------------------------------------- geometry
    @property
    def per_page(self) -> int:
        return self.columns * self.rows_per_page

    @property
    def page(self) -> int:
        return self.index // self.per_page if self.per_page else 0

    @property
    def pages(self) -> int:
        if not self.per_page:
            return 1
        return max(1, (self.count + self.per_page - 1) // self.per_page)

    def page_range(self) -> Tuple[int, int]:
        start = self.page * self.per_page
        return start, min(self.count, start + self.per_page)

    def rect_for(self, i: int) -> pygame.Rect:
        """Screen rect of item ``i``, positioned within its own page."""
        local = i - self.page * self.per_page
        col = local % self.columns
        row = local // self.columns
        return pygame.Rect(
            self.ox + col * (self.cell_w + self.gap_x),
            self.oy + row * (self.cell_h + self.gap_y),
            self.cell_w, self.cell_h)

    # ------------------------------------------------------------ navigation
    def clamp(self) -> None:
        if self.count <= 0:
            self.index = 0
        else:
            self.index = max(0, min(self.count - 1, self.index))

    def move(self, dx: int, dy: int) -> bool:
        if self.count <= 0:
            return False
        before = self.index
        self.index += dx + dy * self.columns
        self.clamp()
        return self.index != before

    def turn_page(self, delta: int) -> bool:
        if self.pages <= 1:
            return False
        before = self.index
        self.index = max(0, min(self.count - 1, self.index + delta * self.per_page))
        return self.index != before

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """'move', 'activate', or None."""
        if event.type == pygame.MOUSEMOTION:
            start, end = self.page_range()
            for i in range(start, end):
                if self.rect_for(i).collidepoint(event.pos):
                    if i != self.index:
                        self.index = i
                        return "move"
                    return None
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            start, end = self.page_range()
            for i in range(start, end):
                if self.rect_for(i).collidepoint(event.pos):
                    self.index = i
                    return "activate"
            return None

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_a):
                return "move" if self.move(-1, 0) else None
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                return "move" if self.move(1, 0) else None
            if event.key in (pygame.K_UP, pygame.K_w):
                return "move" if self.move(0, -1) else None
            if event.key in (pygame.K_DOWN, pygame.K_s):
                return "move" if self.move(0, 1) else None
            if event.key == pygame.K_PAGEUP:
                return "move" if self.turn_page(-1) else None
            if event.key == pygame.K_PAGEDOWN:
                return "move" if self.turn_page(1) else None
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return "activate"
        return None


# --------------------------------------------------------------------------
# Toasts
# --------------------------------------------------------------------------


class Toast:
    __slots__ = ("msg", "life", "full", "color")

    def __init__(self, msg: str, life: float, color: Sequence[int]) -> None:
        self.msg = msg
        self.life = life
        self.full = life
        self.color = color


class Toasts:
    """Short confirmations: purchases, unlocks, mission claims."""

    def __init__(self) -> None:
        self.items: List[Toast] = []

    def push(self, msg: str, color: Sequence[int] = UI_GOOD, life: float = 2.6) -> None:
        self.items.append(Toast(msg, life, color))
        if len(self.items) > 4:
            del self.items[0]

    def clear(self) -> None:
        self.items.clear()

    def update(self, dt: float) -> None:
        for t in self.items:
            t.life -= dt
        self.items = [t for t in self.items if t.life > 0.0]

    def draw(self, surf: pygame.Surface, fonts: Fonts) -> None:
        font = fonts.get("body", bold=True)
        y = HEIGHT - 120
        for t in reversed(self.items):
            fade = min(1.0, t.life / 0.45)
            tw = font.size(t.msg)[0]
            w, h = tw + 40, font.get_height() + 18
            rect = pygame.Rect(WIDTH // 2 - w // 2, y, w, h)
            chip = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(chip, (*UI_PANEL, int(238 * fade)), (0, 0, w, h), border_radius=9)
            pygame.draw.rect(chip, (*t.color, int(255 * fade)), (0, 0, w, h), width=2,
                             border_radius=9)
            surf.blit(chip, rect.topleft)
            text_center(surf, t.msg, font, rect.centerx, rect.centery, t.color, shadow=False)
            y -= h + 8


# --------------------------------------------------------------------------
# Screen framework
# --------------------------------------------------------------------------


class Screen:
    """Base class for every one of the game's twelve states.

    ``game`` is the main.Game instance, which is how a screen reaches the save,
    the wallet, audio, fonts, toasts and ``goto()``. Screens never talk to each
    other directly - they only ask the game to change state.
    """

    #: Music track this screen wants playing, or None to leave it alone.
    track: Optional[str] = None

    def __init__(self, game) -> None:
        self.game = game

    @property
    def fonts(self) -> "Fonts":
        return self.game.fonts

    @property
    def save(self):
        return self.game.save

    @property
    def wallet(self):
        return self.game.wallet

    @property
    def audio(self):
        return self.game.audio

    # Overridden as needed by subclasses.
    def enter(self, **kwargs) -> None:
        """Called every time the screen becomes active."""

    def leave(self) -> None:
        """Called when the screen stops being active."""

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle one input event."""

    def update(self, dt: float) -> None:
        """Advance time."""

    def draw(self, surf: pygame.Surface) -> None:
        """Render a frame."""


def header(surf: pygame.Surface, fonts: "Fonts", title: str, subtitle: str = "",
           balance: Optional[int] = None) -> int:
    """Standard screen header. Returns the y below it."""
    text(surf, title, fonts.get("big", bold=True), 40, 26, UI_TEXT)
    if subtitle:
        text(surf, subtitle, fonts.get("small"), 42, 74, UI_TEXT_DIM, shadow=False)
    if balance is not None:
        coin_pill(surf, balance, fonts.get("body", bold=True), WIDTH - 30, 30)
    pygame.draw.line(surf, UI_BORDER, (40, 104), (WIDTH - 40, 104), 2)
    return 118


def footer_hint(surf: pygame.Surface, fonts: "Fonts", hint: str) -> None:
    pygame.draw.line(surf, UI_BORDER, (40, HEIGHT - 46), (WIDTH - 40, HEIGHT - 46), 2)
    text_center(surf, hint, fonts.get("tiny"), WIDTH // 2, HEIGHT - 28, UI_TEXT_DIM,
                shadow=False)


# --------------------------------------------------------------------------
# In-run HUD
# --------------------------------------------------------------------------


def draw_hud(surf: pygame.Surface, fonts: Fonts, session, wallet,
             show_fps: bool = False, fps: float = 0.0) -> None:
    """Score, progress, DOWN, active power-ups and the combo badge."""
    small = fonts.get("small", bold=True)
    tiny = fonts.get("tiny")
    body = fonts.get("body", bold=True)
    big = fonts.get("big", bold=True)

    # --- score + level, top left -----------------------------------------
    plate = panel(surf, (18, 16, 340, 96), fill=(*UI_PANEL[:3],), radius=11)
    text(surf, session.plan.name if session.plan else "RUN", small, plate.x + 16,
         plate.y + 11, UI_ACCENT)
    text(surf, f"{session.score:,}", big, plate.x + 16, plate.y + 31, UI_TEXT)
    dist = f"{int(session.distance_m)} / {int(session.plan.distance_m)} m" if session.plan else ""
    text(surf, dist, tiny, plate.right - 16, plate.y + 16, UI_TEXT_DIM, right=True,
         shadow=False)
    progress_bar(surf, (plate.x + 16, plate.bottom - 18, plate.w - 32, 9), session.progress)

    # --- DOWN, top right --------------------------------------------------
    coin_pill(surf, wallet.display_int, body, WIDTH - 18, 18)

    # --- combo ------------------------------------------------------------
    if session.combo_tier > 1:
        badge = voxel.combo_badge(session.combo_tier, 62)
        bx = WIDTH - 92
        by = 78
        surf.blit(badge, (bx, by))
        text_center(surf, f"x{1.0 + (session.combo_tier - 1) * 0.25:.2f}", tiny,
                    bx + 31, by + 74, UI_GOLD)
        # A thin ring showing how long the combo has left.
        frac = max(0.0, min(1.0, session.combo_timer / 4.5))
        progress_bar(surf, (bx - 4, by + 64, 70, 5), frac, fill=UI_GOLD, border=False)

    # --- active power-ups, left column ------------------------------------
    y = 130
    for kind in session.powerups.active_kinds():
        icon = voxel.powerup_icon(kind, 40)
        surf.blit(icon, (24, y))
        frac = session.powerups.fraction(kind)
        color = voxel.POWERUP_COLORS.get(kind, UI_ACCENT)
        progress_bar(surf, (72, y + 12, 148, 12), frac, fill=color)
        text(surf, f"{session.powerups.remaining(kind):.1f}s", tiny, 228, y + 11,
             UI_TEXT_DIM, shadow=False)
        y += 50

    if show_fps:
        text(surf, f"{fps:5.1f} fps", tiny, WIDTH - 18, HEIGHT - 26, UI_TEXT_DIM,
             right=True, shadow=False)


def draw_controls_hint(surf: pygame.Surface, fonts: Fonts, alpha: float) -> None:
    """Fades in over the run-up of the very first level."""
    if alpha <= 0.01:
        return
    font = fonts.get("body", bold=True)
    lines = ("A / D  or  ARROWS - change lane",
             "W / SPACE - jump",
             "S - slide",
             "ESC - pause")
    w, h = 430, 26 * len(lines) + 28
    card = pygame.Surface((w, h), pygame.SRCALPHA)
    a = int(230 * max(0.0, min(1.0, alpha)))
    pygame.draw.rect(card, (*UI_PANEL, a), (0, 0, w, h), border_radius=10)
    pygame.draw.rect(card, (*UI_ACCENT, a), (0, 0, w, h), width=2, border_radius=10)
    for i, line in enumerate(lines):
        img = font.render(line, True, UI_TEXT)
        img.set_alpha(a)
        card.blit(img, (20, 14 + i * 26))
    surf.blit(card, (WIDTH // 2 - w // 2, HEIGHT - h - 40))
