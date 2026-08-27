"""
build.py - Package BLOCK ADVENTURE into a single executable.

    python build.py

Produces one self-contained file in ``dist/``:

    Windows   dist/BlockAdventure.exe
    Linux     dist/BlockAdventure
    macOS     dist/BlockAdventure

IMPORTANT: PyInstaller does not cross-compile. Running this on Linux produces a
*Linux* binary, not a .exe. To get a Windows executable you need one of:

  1. GitHub Actions          - see .github/workflows/build.yml (free, no Windows PC)
  2. A Windows machine       - install Python, then run this script there
  3. Wine on this machine    - see --help-wine

The build itself is unusually simple because the game ships no assets: every
sprite and sound is generated at runtime, so there is nothing to bundle beyond
the code and the pygame runtime.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(ROOT, "BlockAdventure.spec")
BUILD_DIR = os.path.join(ROOT, "build")
DIST_DIR = os.path.join(ROOT, "dist")

WINE_HELP = """
Building a Windows .exe under Wine on Linux
-------------------------------------------
This works but is fiddly, and the resulting .exe is best tested on real Windows.

  1. Install Wine:
       sudo apt update && sudo apt install -y wine64 winetricks

  2. Fetch a Windows Python installer (3.11 is a safe choice):
       wget https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe

  3. Install it inside Wine:
       wine python-3.11.9-amd64.exe /quiet InstallAllUsers=1 PrependPath=1

  4. Install the dependencies into the Wine Python:
       wine python -m pip install pygame pyinstaller

  5. Build:
       wine python -m PyInstaller BlockAdventure.spec --noconfirm

  6. The result is dist/BlockAdventure.exe

If Wine gives you trouble, GitHub Actions is far less painful - it needs no
Windows machine and no Wine, just a push to a repo.
"""


def _run(cmd: list, **kwargs) -> int:
    print(">", " ".join(cmd))
    return subprocess.call(cmd, **kwargs)


def _have(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def ensure_deps(python: str) -> bool:
    missing = [m for m in ("pygame", "PyInstaller") if not _have(m)]
    if not missing:
        return True
    print(f"missing: {', '.join(missing)}")
    print("installing...")
    return _run([python, "-m", "pip", "install", "pygame", "pyinstaller"]) == 0


def make_icon(python: str) -> bool:
    tool = os.path.join(ROOT, "tools", "make_icon.py")
    if not os.path.exists(tool):
        print("! tools/make_icon.py missing - building without an icon")
        return False
    return _run([python, tool, BUILD_DIR]) == 0


def selftest(python: str) -> bool:
    """Never package a build that cannot boot."""
    env = dict(os.environ)
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    code = _run([python, os.path.join(ROOT, "game", "main.py"),
                 "--selftest", "--seconds", "4"], env=env)
    return code == 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build BLOCK ADVENTURE")
    parser.add_argument("--help-wine", action="store_true",
                        help="print instructions for building a .exe under Wine")
    parser.add_argument("--skip-selftest", action="store_true",
                        help="package without booting the game first")
    parser.add_argument("--clean", action="store_true",
                        help="remove build/ and dist/ first")
    args = parser.parse_args(argv)

    if args.help_wine:
        print(WINE_HELP)
        return 0

    python = sys.executable
    windows = os.name == "nt"
    target = "BlockAdventure.exe" if windows else "BlockAdventure"

    print(f"python   {python}")
    print(f"platform {sys.platform}")
    print(f"target   dist/{target}")
    if not windows:
        print("\nNOTE: this is not a Windows build. PyInstaller cannot")
        print("cross-compile - see `python build.py --help-wine` or")
        print(".github/workflows/build.yml for a real .exe.\n")

    if args.clean:
        for path in (BUILD_DIR, DIST_DIR):
            if os.path.isdir(path):
                print(f"removing {path}")
                shutil.rmtree(path, ignore_errors=True)

    if not ensure_deps(python):
        print("FAILED: could not install dependencies")
        return 1

    os.makedirs(BUILD_DIR, exist_ok=True)
    make_icon(python)

    if not args.skip_selftest:
        print("\n--- selftest ---")
        if not selftest(python):
            print("\nFAILED: the game does not boot, so it was not packaged.")
            print("Fix the errors above, or pass --skip-selftest to override.")
            return 1
        print("--- selftest passed ---\n")

    if _run([python, "-m", "PyInstaller", SPEC, "--noconfirm"], cwd=ROOT) != 0:
        print("FAILED: PyInstaller returned an error")
        return 1

    out = os.path.join(DIST_DIR, target)
    if not os.path.exists(out):
        print(f"FAILED: expected {out} but it is not there")
        return 1

    size_mb = os.path.getsize(out) / (1024 * 1024)
    if not windows:
        os.chmod(out, 0o755)
    print(f"\ndone: {out}  ({size_mb:.1f} MB)")
    print("This one file is the whole game - no install, no assets, no Python needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
