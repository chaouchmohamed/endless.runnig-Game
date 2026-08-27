"""
currency.py - The DOWN economy.

DOWN is the single currency in BLOCK ADVENTURE. Every gain and every purchase
goes through this class so the balance can never drift out of sync with the
save file, and so the UI can show a rolling "+250 DOWN" ticker.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple


def format_down(amount: int | float) -> str:
    """1250 -> '1,250'."""
    try:
        return f"{int(amount):,}"
    except (TypeError, ValueError):
        return "0"


class Wallet:
    """Holds the player's DOWN balance, backed by the save file."""

    def __init__(self, save) -> None:
        self.save = save
        # Recent transactions, used by the HUD/menu ticker: (amount, reason)
        self.recent: List[Tuple[int, str]] = []
        self.on_change: Optional[Callable[[int, str], None]] = None
        # Smoothed value the UI counts up/down toward.
        self.display = float(self.balance)

    # --------------------------------------------------------------- state
    @property
    def balance(self) -> int:
        return int(self.save.data.get("down", 0))

    @balance.setter
    def balance(self, value: int) -> None:
        self.save.data["down"] = max(0, int(value))
        self.save.mark_dirty()

    @property
    def lifetime(self) -> int:
        return int(self.save.data.get("lifetime_down", 0))

    def can_afford(self, price: int) -> bool:
        return self.balance >= int(price)

    # ------------------------------------------------------------ mutation
    def add(self, amount: int, reason: str = "") -> int:
        """Credit DOWN. Returns the amount actually added."""
        amount = int(amount)
        if amount <= 0:
            return 0
        self.balance = self.balance + amount
        self.save.data["lifetime_down"] = self.lifetime + amount
        self._log(amount, reason)
        return amount

    def spend(self, amount: int, reason: str = "") -> bool:
        """Debit DOWN if affordable. Returns True on success."""
        amount = int(amount)
        if amount < 0 or not self.can_afford(amount):
            return False
        self.balance = self.balance - amount
        self._log(-amount, reason)
        return True

    def _log(self, delta: int, reason: str) -> None:
        self.recent.append((delta, reason))
        if len(self.recent) > 24:
            del self.recent[:-24]
        if self.on_change:
            self.on_change(delta, reason)

    # ------------------------------------------------------------ UI helper
    def update(self, dt: float) -> None:
        """Ease the displayed number toward the real balance."""
        target = float(self.balance)
        diff = target - self.display
        if abs(diff) < 0.6:
            self.display = target
        else:
            self.display += diff * min(1.0, dt * 9.0)

    @property
    def display_int(self) -> int:
        return int(round(self.display))

    def text(self) -> str:
        return format_down(self.display_int)
