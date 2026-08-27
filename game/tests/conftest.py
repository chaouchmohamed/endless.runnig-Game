"""Pytest configuration: put the game package on the import path.

The game modules import each other flatly (``import settings``), which works
when main.py runs because Python adds the script's directory to sys.path. Tests
live one level down, so they add it explicitly.
"""

from __future__ import annotations

import os
import sys

import pytest

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if GAME_DIR not in sys.path:
    sys.path.insert(0, GAME_DIR)

# Never touch a real display or sound card from the test suite.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture()
def save(tmp_path):
    """A SaveManager backed by a throwaway file."""
    from save_system import SaveManager

    return SaveManager(str(tmp_path / "save.json"))


@pytest.fixture()
def wallet(save):
    from currency import Wallet

    return Wallet(save)
