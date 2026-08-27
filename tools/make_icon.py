"""
make_icon.py - Generate the application icon from code.

The game ships no art files, so its icon is drawn too. This writes a real
multi-resolution Windows ``.ico`` (16/24/32/48/64/128/256 px) plus a PNG for
Linux desktop entries.

Pygame cannot write ICO, so the container is assembled by hand: an ICONDIR
header, one ICONDIRENTRY per size, then the PNG blobs. Embedding PNG rather than
BMP is valid for Vista and later and keeps the file small.

    python tools/make_icon.py [outdir]
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
from typing import List, Tuple

# Run from a checkout without installing anything.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GAME = os.path.join(_ROOT, "game")
if _GAME not in sys.path:
    sys.path.insert(0, _GAME)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (must follow the sys.path setup)

import voxel  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)

BG_TOP = (26, 34, 52)
BG_BOTTOM = (14, 19, 30)
GOLD = (255, 202, 64)
GOLD_DARK = (198, 138, 24)
ROAD = (104, 112, 128)
STRIPE = (238, 238, 226)


def _draw_icon(size: int) -> pygame.Surface:
    """A blocky gold D on a dark tile, over a hint of receding road.

    Detail is dropped at small sizes rather than scaled down, so 16x16 stays
    legible instead of turning to mush.
    """
    s = voxel.make_surface(size, size)
    u = size / 32.0                      # one design unit, in pixels
    radius = max(2, int(size * 0.16))

    # Background: vertical gradient, drawn as bands.
    bands = max(4, size // 8)
    for i in range(bands):
        t = i / max(1, bands - 1)
        color = voxel.mix(BG_TOP, BG_BOTTOM, t)
        y0 = int(size * i / bands)
        y1 = int(size * (i + 1) / bands)
        pygame.draw.rect(s, color, (0, y0, size, max(1, y1 - y0)))

    # Road wedge, so the icon reads as a runner even at a glance.
    if size >= 24:
        pygame.draw.polygon(s, ROAD, [
            (size * 0.42, size * 0.52), (size * 0.58, size * 0.52),
            (size * 0.84, size), (size * 0.16, size)])
        if size >= 48:
            pygame.draw.polygon(s, STRIPE, [
                (size * 0.485, size * 0.60), (size * 0.515, size * 0.60),
                (size * 0.55, size * 0.86), (size * 0.45, size * 0.86)])

    # The D, built from blocks like the in-game coin.
    if size >= 20:
        bw = max(2, int(3 * u))          # stroke width
        x = size * 0.30
        y = size * 0.16
        h = size * 0.46
        w = size * 0.34
        pygame.draw.rect(s, GOLD, (x, y, bw, h))                       # spine
        pygame.draw.rect(s, GOLD, (x, y, w * 0.72, bw))                # top
        pygame.draw.rect(s, GOLD, (x, y + h - bw, w * 0.72, bw))       # bottom
        pygame.draw.rect(s, GOLD, (x + w * 0.72 - bw, y + bw * 0.8,
                                   bw, h - bw * 2.6))                  # bowl
        if size >= 48:
            pygame.draw.rect(s, voxel.lighten(GOLD, 0.45), (x, y, bw, max(1, int(2 * u))))
    else:
        # At 16px, a solid gold block reads better than any letter.
        pygame.draw.rect(s, GOLD, (size * 0.30, size * 0.20,
                                   size * 0.40, size * 0.42))
        pygame.draw.rect(s, GOLD_DARK, (size * 0.30, size * 0.20,
                                        size * 0.40, size * 0.42), 1)

    # Border last, so nothing overlaps it.
    pygame.draw.rect(s, voxel.lighten(BG_TOP, 0.22), (0, 0, size, size),
                     width=max(1, int(u)), border_radius=radius)
    return s


def _png_bytes(surf: pygame.Surface) -> bytes:
    """PNG-encode a surface. pygame needs a real path, so use a temp file."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        pygame.image.save(surf, path)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def write_ico(path: str, images: List[Tuple[int, bytes]]) -> None:
    """Assemble an ICO from PNG blobs."""
    count = len(images)
    out = [struct.pack("<HHH", 0, 1, count)]
    offset = 6 + 16 * count
    entries = []
    blobs = []
    for size, blob in images:
        # 0 means 256 in the ICO header.
        dim = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                   len(blob), offset))
        offset += len(blob)
        blobs.append(blob)
    with open(path, "wb") as fh:
        fh.write(out[0])
        for e in entries:
            fh.write(e)
        for b in blobs:
            fh.write(b)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    outdir = os.path.abspath(argv[0]) if argv else os.path.join(_ROOT, "build")
    os.makedirs(outdir, exist_ok=True)

    pygame.init()
    try:
        images = [(size, _png_bytes(_draw_icon(size))) for size in SIZES]

        ico = os.path.join(outdir, "icon.ico")
        write_ico(ico, images)
        print(f"wrote {ico} ({os.path.getsize(ico):,} bytes, {len(SIZES)} sizes)")

        png = os.path.join(outdir, "icon.png")
        pygame.image.save(_draw_icon(256), png)
        print(f"wrote {png} ({os.path.getsize(png):,} bytes)")
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
