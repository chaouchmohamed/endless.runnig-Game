"""
settings.py - Global configuration for BLOCK ADVENTURE.

Every tunable constant lives here so the whole game can be re-balanced without
touching gameplay code. Nothing in this module imports pygame, which keeps it
safe to import from tests and tools.
"""

from __future__ import annotations

import os
import sys

# --------------------------------------------------------------------------
# Paths
#
# ``FROZEN`` is true inside a PyInstaller build. That matters because a one-file
# build unpacks itself into a temporary directory that is deleted on exit, so a
# save written next to the executable would be lost every time. Packaged builds
# therefore keep the profile in the platform's own user-data directory, while a
# checkout keeps it in game/data/ where it is easy to inspect.
# --------------------------------------------------------------------------
FROZEN = bool(getattr(sys, "frozen", False))

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(GAME_DIR, "assets")
CHAR_ASSETS = os.path.join(ASSETS_DIR, "characters")
WORLD_ASSETS = os.path.join(ASSETS_DIR, "worlds")
COIN_ASSETS = os.path.join(ASSETS_DIR, "coins")
OBSTACLE_ASSETS = os.path.join(ASSETS_DIR, "obstacles")
SOUND_ASSETS = os.path.join(ASSETS_DIR, "sounds")
UI_ASSETS = os.path.join(ASSETS_DIR, "ui")

APP_DIR_NAME = "BlockAdventure"


def user_data_dir() -> str:
    """Per-user, writable, and outside anything an installer would replace."""
    home = os.path.expanduser("~")
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(base, APP_DIR_NAME)
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", APP_DIR_NAME)
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "block-adventure")


# BA_SAVE_DIR overrides both, which is what the test suite and --selftest use.
_override = os.environ.get("BA_SAVE_DIR")
if _override:
    DATA_DIR = os.path.abspath(_override)
elif FROZEN:
    DATA_DIR = user_data_dir()
else:
    DATA_DIR = os.path.join(GAME_DIR, "data")
SAVE_PATH = os.path.join(DATA_DIR, "save.json")

GAME_TITLE = "BLOCK ADVENTURE"
GAME_TAGLINE = "LET'S START THE ADVENTURE!"
SAVE_VERSION = 1

# --------------------------------------------------------------------------
# Display / performance
# --------------------------------------------------------------------------
WIDTH = 1280
HEIGHT = 720
CX = WIDTH // 2
FPS = 60
MAX_DT = 1.0 / 20.0          # clamp delta time so a stall never teleports the player
VSYNC = True

# --------------------------------------------------------------------------
# Pseudo-3D projection
#
#   world space: x = lateral (0 = middle lane), y = up (0 = road surface),
#                z = depth ahead of the player (0 = player, grows into screen)
#
#   scale   = FOCAL / (z + CAM_Z)
#   screen  = (CX + x * scale, HORIZON_Y + (CAM_HEIGHT - y) * scale)
# --------------------------------------------------------------------------
HORIZON_Y = 252.0
FOCAL = 520.0
CAM_HEIGHT = 210.0           # camera eye height above the road
CAM_Z = 300.0                # camera sits this far behind the player
NEAR_Z = -260.0              # cull anything closer than this (behind camera)
BASE_DRAW_Z = 1900.0         # minimum draw distance
MAX_DRAW_Z = 4400.0          # draw distance at top speed
DRAW_Z_PER_SPEED = 1.7       # extra draw distance per unit of run speed

LANE_COUNT = 3
LANE_W = 132.0               # lateral distance between lane centres
LANE_X = (-LANE_W, 0.0, LANE_W)
ROAD_HALF = 250.0            # half width of the road surface
SHOULDER = 120.0             # width of the decorated verge either side
STRIPE_LEN = 150.0           # length of one road texture band (speed feel)

METER = 12.0                 # world units per in-game metre

# --------------------------------------------------------------------------
# Player physics
# --------------------------------------------------------------------------
PLAYER_W = 78.0              # collision width  (world units)
PLAYER_H = 112.0             # collision height (standing)
PLAYER_D = 62.0              # collision depth
SLIDE_H_FACTOR = 0.44        # hitbox height while sliding
SLIDE_TIME = 0.55
SLIDE_COOLDOWN = 0.06
GRAVITY = 1500.0
JUMP_V = 540.0               # -> 0.72 s airtime, ~97 units peak height
SUPER_JUMP_MULT = 1.34
LANE_SWITCH_TIME = 0.115     # snappy but readable
COYOTE_TIME = 0.09           # jump grace after leaving the ground
INPUT_BUFFER = 0.16          # remembers a press made slightly too early
INVULN_AFTER_HIT = 1.15      # not used for death, used by shield/revive feedback

# --------------------------------------------------------------------------
# Run pacing
# --------------------------------------------------------------------------
SPEED_BASE = 600.0           # world units / second at level 1
SPEED_MAX = 1720.0           # hard ceiling (level 200)
SPEED_RAMP = 0.55            # in-run acceleration per second toward level cap
SPEED_BOOST_MULT = 1.45
SLOWMO_MULT = 0.58
POWERUP_BASE_TIME = {
    "magnet": 8.0,
    "shield": 12.0,
    "coin_multiplier": 10.0,
    "speed_boost": 6.0,
    "super_jump": 10.0,
    "slow_motion": 6.0,
}
POWERUP_UPGRADE_STEP = 0.22   # +22% duration per upgrade level
POWERUP_MAX_LEVEL = 5
POWERUP_UPGRADE_COST = (0, 1200, 3600, 9000, 22000, 55000)

MAGNET_RANGE = 430.0
COIN_MULT_VALUE = 2

# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
SCORE_PER_METER = 1.0
SCORE_PER_COIN = 12
SCORE_PER_POWERUP = 60
SCORE_PER_DODGE = 15         # awarded per obstacle row cleared
COMBO_STEP = 5               # every N dodges -> +1 combo tier
COMBO_MAX_TIER = 8
COMBO_TIMEOUT = 4.5

COIN_VALUE = 1               # Down per coin

# --------------------------------------------------------------------------
# Rarity
# --------------------------------------------------------------------------
RARITY_ORDER = ("COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC")
RARITY_PRICE = {
    "COMMON": 500,
    "UNCOMMON": 1_500,
    "RARE": 5_000,
    "EPIC": 15_000,
    "LEGENDARY": 50_000,
    "MYTHIC": 150_000,
}
RARITY_COLOR = {
    "COMMON": (176, 186, 198),
    "UNCOMMON": (104, 214, 124),
    "RARE": (86, 168, 255),
    "EPIC": (188, 118, 255),
    "LEGENDARY": (255, 186, 62),
    "MYTHIC": (255, 96, 148),
}

# --------------------------------------------------------------------------
# UI palette
# --------------------------------------------------------------------------
UI_BG = (17, 22, 34)
UI_PANEL = (28, 36, 54)
UI_PANEL_LIGHT = (40, 51, 74)
UI_BORDER = (68, 84, 118)
UI_TEXT = (238, 244, 255)
UI_TEXT_DIM = (150, 164, 190)
UI_ACCENT = (86, 204, 255)
UI_ACCENT_DARK = (36, 132, 190)
UI_GOOD = (104, 214, 124)
UI_BAD = (255, 96, 96)
UI_GOLD = (255, 202, 64)
UI_GOLD_DARK = (198, 138, 24)
UI_SHADOW = (8, 11, 18)

# --------------------------------------------------------------------------
# Game states
# --------------------------------------------------------------------------
class State:
    INTRO = "INTRO"
    MENU = "MENU"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    SHOP = "SHOP"
    CHARACTERS = "CHARACTERS"
    WORLDS = "WORLDS"
    LEVEL_SELECT = "LEVEL_SELECT"
    MISSIONS = "MISSIONS"
    GAME_OVER = "GAME_OVER"
    LEVEL_COMPLETE = "LEVEL_COMPLETE"
    SETTINGS = "SETTINGS"


TRANSITION_TIME = 0.26

# --------------------------------------------------------------------------
# Progression
# --------------------------------------------------------------------------
MAX_LEVEL = 200
FINAL_LEVEL = 200
FINAL_LEVEL_NAME = "THE FINAL ADVENTURE"
FINAL_LEVEL_REWARD = 250_000

# Distance anchors (level, metres). Interpolated for every other level so the
# curve is smooth, monotonic and hits the designed checkpoints exactly.
DISTANCE_ANCHORS = (
    (1, 500), (5, 700), (10, 900), (18, 1150), (25, 1350), (40, 1750),
    (50, 2000), (65, 2400), (75, 2700), (90, 3150), (100, 3500),
    (115, 3900), (125, 4200), (140, 4700), (150, 5000), (165, 5450),
    (175, 5950), (190, 6550), (200, 7000),
)

# Level bands unlock new mechanics (see level.py).
BAND_MOVING = 11             # lane-shifting obstacles
BAND_JUMPY = 21              # pits / low hurdles become common
BAND_FAST = 31               # speed multiplier climbs
BAND_COMBO = 51              # multi-lane combinations
BAND_ADVANCED = 76           # long patterned trains
BAND_VERYFAST = 101
BAND_EXTREME = 151

DEBUG = bool(os.environ.get("BA_DEBUG"))
