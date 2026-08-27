# BLOCK ADVENTURE

we need to try every thing and build every thing >

A pseudo-3D, three-lane runner with 200 hand-paced levels, 25 characters, 8 worlds
and 6 upgradeable power-ups.

Every pixel and every sound is **generated at runtime** — there are no art or audio
files anywhere in this project. Characters, obstacles, scenery, coins and UI icons
are drawn out of shaded cubes (`voxel.py`); sound effects and the three chiptune
loops are synthesized from wavetables (`audio.py`).

## Running it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python game/main.py
```

## Controls

| Key | Action |
|---|---|
| `A` / `D` or `←` / `→` | Change lane |
| `W` / `SPACE` / `↑` | Jump |
| `S` / `↓` | Slide (in the air, dive then slide on landing) |
| `ESC` / `P` | Pause |
| `ENTER` | Select |
| `F1` | Toggle the FPS counter |

Menus work with the keyboard *or* the mouse throughout.

## How a run works

Reach the level's target distance without hitting anything. Each obstacle's
**shape** tells you what to do — low things are jumped, floating things are slid
under, full-height things must be gone around.

Score comes from distance, coins, power-ups and dodges. Dodging consecutively
builds a **combo tier** (up to x8) that multiplies everything you earn while it
lasts, so pressing your luck pays. Coins are **DOWN**, the game's only currency,
and they are what buy characters, worlds and power-up upgrades.

Stars are the long game: 1 for finishing, 2 and 3 for score.

## Level design

Levels are **deterministic** — level 137 is identical on every attempt, so it can
be learned rather than merely survived. They are also **provably solvable**: the
generator tracks a notional safe lane and refuses to emit a row the player cannot
reach in time, and `tests/test_level.py` re-verifies that across all 200 levels on
every test run.

Difficulty arrives in bands rather than as a smooth grind, each unlocking a new
mechanic (see `settings.py`):

| Level | Unlocks |
|---|---|
| 11 | Lane-shifting obstacles |
| 21 | Pits and hurdles become common |
| 31 | Speed climbs; trains appear |
| 51 | Multi-lane combinations |
| 76 | Long patterned trains, crushers |
| 101 | Faster still |
| 151 | Extreme density |
| 200 | **THE FINAL ADVENTURE** |

Each of the 8 worlds themes 25 consecutive levels; with *Auto World Theme* on, the
scenery changes as you progress through any world you own.

## Architecture

```
settings.py       every tunable constant - balance the whole game from here
camera.py         the one pseudo-3D projection
voxel.py          runtime sprite engine + scaled-sprite cache
save_system.py    atomic JSON saves, corruption recovery, sanitization
currency.py       the DOWN wallet
player.py         lane physics + the 25-character roster
world.py          8 worlds and the road renderer
obstacles.py      8 hazards as real 3D boxes; one AABB collision test
collectibles.py   coins, pickups, magnet attraction
powerups.py       the 6 power-ups, durations and upgrade costs
level.py          the 200-level curve and the solvable generator
run.py            one live run: the only place gameplay rules are applied
particles.py      effects and screen shake
audio.py          synthesized SFX and music
ui.py             fonts, widgets, HUD
screens.py        8 screens
shop.py           the 3 purchase screens
main.py           entry point and state machine
```

Two conventions hold everywhere: **all balance lives in `settings.py`**, and money
only ever moves through `currency.Wallet`, so the balance and the save file cannot
drift apart.

## Rebalancing

Almost everything worth tuning is one constant in `settings.py`:

| To change | Edit |
|---|---|
| Jump arc | `JUMP_V`, `GRAVITY` |
| Lane-switch snap | `LANE_SWITCH_TIME` |
| Difficulty ramp | `SPEED_BASE`, `SPEED_MAX`, `SPEED_RAMP` |
| Level lengths | `DISTANCE_ANCHORS` |
| Prices | `RARITY_PRICE`, `POWERUP_UPGRADE_COST` |
| Combo generosity | `COMBO_STEP`, `COMBO_TIMEOUT`, `COMBO_MAX_TIER` |
| Input forgiveness | `COYOTE_TIME`, `INPUT_BUFFER` |

## Testing

```bash
.venv/bin/python -m pytest game/tests -q          # unit tests
.venv/bin/python game/main.py --selftest          # headless boot of every state
```

The self-test needs no display: it steps every screen, plays scripted runs at
levels 1 / 2 / 25 / 60 / 120 / 200 with a simple autopilot, checks the sprite cache
stays bounded, and verifies a save round-trip.

```bash
.venv/bin/python game/main.py --level 120         # jump straight into a level
BA_DEBUG=1 .venv/bin/python game/main.py         # debug flag
```

## Save data

Where the profile lives depends on how the game was started:

| | |
|---|---|
| From a checkout | `game/data/save.json` |
| From a packaged build | `%APPDATA%\BlockAdventure\` (Windows) · `~/.local/share/block-adventure/` (Linux) · `~/Library/Application Support/BlockAdventure/` (macOS) |
| `BA_SAVE_DIR=/some/path` | wherever you point it — used by the tests |

A packaged build must not save next to its own executable: PyInstaller's one-file
mode unpacks into a temp directory that is deleted on exit, so the save would be
lost every time.

The file is written atomically (temp file + `os.replace`) so a crash mid-write
cannot truncate it. A corrupt file is moved aside to `save.json.corrupt` and a
fresh profile starts; a partial or hand-edited file is repaired against the
defaults rather than rejected. *Settings → Reset All Progress* wipes it, and asks
twice.

## Building a standalone executable

One self-contained file, no Python needed on the target machine:

```bash
.venv/bin/pip install pyinstaller
.venv/bin/python build.py
```

`build.py` generates the icon, runs the headless self-test (it refuses to package
a build that cannot boot), then invokes PyInstaller. Output lands in `dist/`.

**PyInstaller cannot cross-compile.** Running the above on Linux produces a Linux
binary, *not* a `.exe`. For a Windows executable, pick one:

| Route | How |
|---|---|
| **GitHub Actions** (easiest — no Windows needed) | Push the repo; `.github/workflows/build.yml` builds Windows + Linux + macOS on every push. Download from the Actions tab, or push a `v*` tag to get a Release. |
| **A Windows PC** | Install Python 3.11+, then `python build.py` there. |
| **Wine, locally** | `python build.py --help-wine` prints the steps. Works, but fiddly — test the result on real Windows. |

Packaging is unusually simple here because the game ships **no asset files** — all
art and audio are generated at runtime, so the build is just code plus the pygame
runtime (~15–25 MB depending on platform).

