"""
audio.py - Every sound in the game, synthesized at runtime.

There are no audio files in this project, matching voxel.py's approach to art.
Sounds are built as 16-bit stereo buffers and handed straight to
``pygame.mixer.Sound(buffer=...)``.

Speed comes from wavetables rather than numpy: each waveform is sampled once
into a 1024-entry table, and rendering a note is then table lookups and adds.
That keeps the module dependency-free. The three music loops are the only
expensive part, so they are generated lazily on a daemon thread - the game never
waits for them.

If the mixer cannot open (no sound card, dummy driver, busy device), ``ok`` is
False and every method here becomes a no-op. Audio is never allowed to be the
reason the game fails to start.
"""

from __future__ import annotations

import array
import math
import random
import threading
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

RATE = 22050
TABLE = 1024
_MAX = 32767
_MIN = -32768

_rng = random.Random(8675309)


# --------------------------------------------------------------------------
# Wavetables
# --------------------------------------------------------------------------

def _build_table(name: str) -> List[float]:
    out: List[float] = []
    for i in range(TABLE):
        p = i / TABLE
        if name == "sine":
            out.append(math.sin(p * math.tau))
        elif name == "square":
            out.append(1.0 if p < 0.5 else -1.0)
        elif name == "saw":
            out.append(2.0 * p - 1.0)
        elif name == "tri":
            out.append(4.0 * abs(p - 0.5) - 1.0)
        elif name == "pulse":
            out.append(1.0 if p < 0.25 else -1.0)
        elif name == "noise":
            out.append(_rng.uniform(-1.0, 1.0))
        else:
            out.append(math.sin(p * math.tau))
    return out


_TABLES: Dict[str, List[float]] = {}


def _table(name: str) -> List[float]:
    t = _TABLES.get(name)
    if t is None:
        t = _build_table(name)
        _TABLES[name] = t
    return t


def _blank(seconds: float) -> array.array:
    """A silent stereo buffer of the given length."""
    frames = max(1, int(seconds * RATE))
    return array.array("h", bytes(frames * 4))


def _render(buf: array.array, at: float, dur: float, freq: float, wave: str,
            vol: float, sweep: float = 1.0, attack: float = 0.004,
            curve: float = 1.6, pan: float = 0.0) -> None:
    """Mix one note into ``buf`` at time ``at`` (seconds).

    ``sweep`` is the pitch ratio reached by the end of the note - 2.0 rises an
    octave, 0.5 falls one. ``pan`` runs -1 (left) to +1 (right).
    """
    table = _table(wave)
    frames = len(buf) // 2
    start = int(at * RATE)
    n = max(1, int(dur * RATE))
    atk = max(1, int(attack * RATE))
    pan = max(-1.0, min(1.0, pan))
    left = 1.0 - max(0.0, pan) * 0.5
    right = 1.0 - max(0.0, -pan) * 0.5

    phase = 0.0
    for i in range(n):
        idx = start + i
        if idx >= frames:
            break
        if idx < 0:
            continue
        prog = i / n
        f = freq * (1.0 + (sweep - 1.0) * prog)
        phase += f * TABLE / RATE
        s = table[int(phase) & (TABLE - 1)]

        amp = vol
        if i < atk:
            amp *= i / atk
        amp *= (1.0 - prog) ** curve

        v = s * amp * _MAX
        j = idx * 2
        a = int(buf[j] + v * left)
        b = int(buf[j + 1] + v * right)
        buf[j] = _MAX if a > _MAX else (_MIN if a < _MIN else a)
        buf[j + 1] = _MAX if b > _MAX else (_MIN if b < _MIN else b)


def _sound(buf: array.array) -> Optional[pygame.mixer.Sound]:
    try:
        return pygame.mixer.Sound(buffer=buf.tobytes())
    except (pygame.error, ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# Sound effects
#
# Each entry is a list of (delay, duration, freq, wave, volume, sweep) notes.
# --------------------------------------------------------------------------

SFX_RECIPES: Dict[str, Tuple[float, List[tuple]]] = {
    "jump":     (0.20, [(0.0, 0.16, 330.0, "square", 0.34, 2.1)]),
    "land":     (0.16, [(0.0, 0.10, 120.0, "sine", 0.40, 0.6),
                        (0.0, 0.09, 400.0, "noise", 0.16, 0.5)]),
    "slide":    (0.28, [(0.0, 0.26, 900.0, "noise", 0.24, 0.35)]),
    "coin":     (0.16, [(0.0, 0.06, 988.0, "square", 0.24, 1.0),
                        (0.05, 0.09, 1319.0, "square", 0.22, 1.0)]),
    "powerup":  (0.40, [(0.00, 0.08, 523.0, "square", 0.24, 1.0),
                        (0.07, 0.08, 659.0, "square", 0.24, 1.0),
                        (0.14, 0.08, 784.0, "square", 0.24, 1.0),
                        (0.21, 0.16, 1047.0, "square", 0.26, 1.0)]),
    "hit":      (0.36, [(0.0, 0.30, 260.0, "saw", 0.40, 0.3),
                        (0.0, 0.16, 800.0, "noise", 0.30, 0.4)]),
    "death":    (0.75, [(0.0, 0.62, 420.0, "saw", 0.36, 0.16),
                        (0.0, 0.30, 600.0, "noise", 0.20, 0.3),
                        (0.34, 0.36, 190.0, "square", 0.26, 0.55)]),
    "shield":   (0.34, [(0.0, 0.30, 300.0, "sine", 0.30, 2.4),
                        (0.06, 0.24, 600.0, "tri", 0.20, 1.6)]),
    "click":    (0.10, [(0.0, 0.05, 720.0, "square", 0.20, 1.0)]),
    "move":     (0.08, [(0.0, 0.04, 480.0, "square", 0.14, 1.0)]),
    "denied":   (0.24, [(0.0, 0.20, 210.0, "saw", 0.26, 0.7)]),
    "purchase": (0.46, [(0.00, 0.10, 523.0, "tri", 0.28, 1.0),
                        (0.09, 0.10, 784.0, "tri", 0.28, 1.0),
                        (0.18, 0.24, 1047.0, "tri", 0.30, 1.0)]),
    "star":     (0.34, [(0.0, 0.14, 1047.0, "sine", 0.28, 1.0),
                        (0.10, 0.22, 1568.0, "sine", 0.26, 1.0)]),
    "combo":    (0.20, [(0.0, 0.07, 880.0, "square", 0.20, 1.0),
                        (0.06, 0.12, 1320.0, "square", 0.20, 1.0)]),
    "complete": (1.10, [(0.00, 0.14, 523.0, "square", 0.28, 1.0),
                        (0.13, 0.14, 659.0, "square", 0.28, 1.0),
                        (0.26, 0.14, 784.0, "square", 0.28, 1.0),
                        (0.39, 0.34, 1047.0, "square", 0.32, 1.0),
                        (0.60, 0.44, 1319.0, "tri", 0.28, 1.0)]),
    "unlock":   (0.60, [(0.00, 0.16, 392.0, "tri", 0.26, 1.0),
                        (0.14, 0.16, 587.0, "tri", 0.26, 1.0),
                        (0.28, 0.30, 880.0, "square", 0.28, 1.0)]),
}


def _build_sfx(name: str) -> Optional[pygame.mixer.Sound]:
    recipe = SFX_RECIPES.get(name)
    if not recipe:
        return None
    length, notes = recipe
    buf = _blank(length)
    for delay, dur, freq, wave, vol, sweep in notes:
        _render(buf, delay, dur, freq, wave, vol, sweep=sweep)
    return _sound(buf)


# --------------------------------------------------------------------------
# Music
#
# Semitone offsets from the track's root, as (offset, beats). None is a rest.
# --------------------------------------------------------------------------

TRACKS: Dict[str, dict] = {
    "menu": {
        "bpm": 98, "root": 220.0, "lead_wave": "square", "bass_wave": "tri",
        "lead": [(0, 1), (7, 1), (12, 1), (10, 1), (7, 2), (5, 1), (3, 1),
                 (0, 1), (3, 1), (7, 1), (12, 1), (10, 2), (7, 1), (5, 1)],
        "bass": [(-12, 2), (-5, 2), (-8, 2), (-3, 2),
                 (-12, 2), (-5, 2), (-10, 2), (-5, 2)],
        "hats": False,
    },
    "run": {
        "bpm": 142, "root": 262.0, "lead_wave": "pulse", "bass_wave": "saw",
        "lead": [(0, 1), (3, 1), (7, 1), (10, 1), (12, 1), (10, 1), (7, 1), (3, 1),
                 (5, 1), (8, 1), (12, 1), (15, 1), (14, 1), (12, 1), (10, 1), (7, 1)],
        "bass": [(-12, 1), (-12, 1), (-5, 1), (-5, 1), (-8, 1), (-8, 1), (-3, 1), (-3, 1),
                 (-12, 1), (-12, 1), (-7, 1), (-7, 1), (-5, 1), (-5, 1), (-10, 1), (-10, 1)],
        "hats": True,
    },
    "final": {
        "bpm": 156, "root": 294.0, "lead_wave": "square", "bass_wave": "saw",
        "lead": [(0, 1), (12, 1), (11, 1), (12, 1), (7, 2), (10, 1), (12, 1),
                 (14, 1), (12, 1), (10, 1), (7, 1), (5, 2), (3, 1), (0, 1)],
        "bass": [(-12, 1), (-12, 1), (-12, 1), (-7, 1), (-10, 1), (-10, 1), (-5, 1), (-5, 1),
                 (-12, 1), (-12, 1), (-8, 1), (-8, 1), (-7, 1), (-7, 1), (-3, 1), (-3, 1)],
        "hats": True,
    },
}


def _semitone(root: float, offset: int) -> float:
    return root * (2.0 ** (offset / 12.0))


def _build_music(name: str) -> Optional[pygame.mixer.Sound]:
    spec = TRACKS.get(name)
    if not spec:
        return None
    beat = 60.0 / spec["bpm"] / 2.0        # eighth notes
    lead_beats = sum(b for _, b in spec["lead"])
    bass_beats = sum(b for _, b in spec["bass"])
    total = max(lead_beats, bass_beats) * beat
    buf = _blank(total + 0.05)

    t = 0.0
    for offset, beats in spec["lead"]:
        dur = beats * beat
        if offset is not None:
            _render(buf, t, dur * 0.94, _semitone(spec["root"], offset),
                    spec["lead_wave"], 0.15, curve=0.9, pan=0.18)
        t += dur

    t = 0.0
    for offset, beats in spec["bass"]:
        dur = beats * beat
        if offset is not None:
            _render(buf, t, dur * 0.9, _semitone(spec["root"], offset),
                    spec["bass_wave"], 0.16, curve=0.7, pan=-0.18)
        t += dur

    if spec.get("hats"):
        steps = int(total / beat)
        for i in range(steps):
            vol = 0.075 if i % 2 else 0.045
            _render(buf, i * beat, beat * 0.34, 5200.0, "noise", vol, curve=2.6)

    return _sound(buf)


# --------------------------------------------------------------------------
# The manager
# --------------------------------------------------------------------------


class Audio:
    """Owns the mixer, the SFX cache and the music channel."""

    MUSIC_CHANNEL = 0

    def __init__(self, save=None) -> None:
        self.save = save
        self.ok = False
        self.sfx: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self.music: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self.current_track: Optional[str] = None
        self._channel: Optional[pygame.mixer.Channel] = None
        self._building: set = set()
        self._lock = threading.Lock()

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(1)
            self._channel = pygame.mixer.Channel(self.MUSIC_CHANNEL)
            self.ok = True
        except (pygame.error, AttributeError):
            self.ok = False

    # -------------------------------------------------------------- settings
    def _cfg(self, key: str, default):
        if not self.save:
            return default
        return self.save.settings.get(key, default)

    @property
    def sfx_on(self) -> bool:
        return bool(self._cfg("sfx", True))

    @property
    def music_on(self) -> bool:
        return bool(self._cfg("music", True))

    @property
    def sfx_volume(self) -> float:
        return float(self._cfg("sfx_volume", 0.75))

    @property
    def music_volume(self) -> float:
        return float(self._cfg("music_volume", 0.55))

    def apply_settings(self) -> None:
        """Re-read the save settings - call after the settings screen changes."""
        if not self.ok:
            return
        if self._channel is not None:
            self._channel.set_volume(self.music_volume if self.music_on else 0.0)
        if not self.music_on:
            self.stop_music()
        elif self.current_track:
            self.play_music(self.current_track, force=True)

    # ------------------------------------------------------------------- sfx
    def play(self, name: str, volume: float = 1.0) -> None:
        if not self.ok or not self.sfx_on:
            return
        if name not in self.sfx:
            # Cache the None too, so a bad name is not re-synthesized every call.
            self.sfx[name] = _build_sfx(name)
        sound = self.sfx[name]
        if sound is None:
            return
        try:
            sound.set_volume(max(0.0, min(1.0, volume * self.sfx_volume)))
            sound.play()
        except pygame.error:
            pass

    def sfx_callback(self):
        """A plain callable for code that only wants to make a noise.

        ``Player.update`` takes an ``sfx`` argument of exactly this shape.
        """
        return lambda name: self.play(name)

    # ----------------------------------------------------------------- music
    def play_music(self, track: str, force: bool = False) -> None:
        if not self.ok or not self.music_on:
            self.current_track = track
            return
        if track == self.current_track and not force and self._playing():
            return
        self.current_track = track

        sound = self.music.get(track)
        if sound is None:
            self._request_music(track)
            return
        self._start(sound)

    def _playing(self) -> bool:
        try:
            return bool(self._channel and self._channel.get_busy())
        except pygame.error:
            return False

    def _start(self, sound: pygame.mixer.Sound) -> None:
        try:
            if self._channel is None:
                return
            self._channel.stop()
            self._channel.set_volume(self.music_volume)
            self._channel.play(sound, loops=-1)
        except pygame.error:
            pass

    def _request_music(self, track: str) -> None:
        """Generate a loop off-thread; start it if it is still wanted."""
        with self._lock:
            if track in self._building:
                return
            self._building.add(track)

        def work() -> None:
            sound = None
            try:
                sound = _build_music(track)
            except Exception:
                sound = None
            with self._lock:
                self.music[track] = sound
                self._building.discard(track)
            if sound is not None and self.current_track == track and self.music_on:
                self._start(sound)

        threading.Thread(target=work, daemon=True, name=f"music:{track}").start()

    def stop_music(self) -> None:
        if not self.ok:
            return
        try:
            if self._channel:
                self._channel.stop()
        except pygame.error:
            pass

    def prewarm(self, names: Sequence[str] = ()) -> None:
        """Build a few short sounds up front so the first press is not late."""
        if not self.ok:
            return
        for name in (names or ("click", "move", "coin", "jump")):
            if name not in self.sfx:
                self.sfx[name] = _build_sfx(name)

    def shutdown(self) -> None:
        self.stop_music()
        try:
            pygame.mixer.quit()
        except pygame.error:
            pass
