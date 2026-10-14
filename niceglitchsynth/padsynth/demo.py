"""Demo transport - built-in loops (chord progressions + optional arps).

The engine applies ``transpose`` (octave up/down) to every pushed note, so the
demo, the pad grid and the keyboard strip all share one octave offset.
"""
from __future__ import annotations

import heapq
import threading
import time

from .util import NOTE_NAMES

SPELLS = {
    "minor": [0, 3, 7, 12, 15],
    "major": [0, 4, 7, 12, 16],
    "min7": [0, 3, 7, 10, 14],
    "maj7": [0, 4, 7, 11, 15],
    "majadd9": [0, 4, 7, 14, 19],
    "sus2": [0, 2, 7, 12, 14],
}

_SPELL_LABEL = {"minor": "m", "major": "", "min7": "m7", "maj7": "M7",
                "majadd9": "M9", "sus2": "sus2"}

PATTERNS = [
    {"name": "EMBER DRIFT", "root": 45, "chords": [0, 8, 3, 10], "spell": "min7",
     "beats": 4, "bpm": 72, "arp": 0.0},
    {"name": "HALO PULSE", "root": 48, "chords": [0, 7, 5, 9], "spell": "majadd9",
     "beats": 4, "bpm": 84, "arp": 0.5},
    {"name": "GLASS EMPIRE", "root": 41, "chords": [0, -5, -2, 3], "spell": "minor",
     "beats": 6, "bpm": 64, "arp": 0.0},
    {"name": "DUSK THREADS", "root": 43, "chords": [0, 5, 10, 3], "spell": "min7",
     "beats": 2, "bpm": 96, "arp": 1.0},
]

_CENTRAL = 72  # keep voices in the singing range


class _Scheduler:
    """Min-heap of (when, fn) fired from the demo thread."""

    def __init__(self):
        self._heap: list[tuple[float, int, callable]] = []
        self._seq = 0

    def at(self, when: float, fn):
        self._seq += 1
        heapq.heappush(self._heap, (when, self._seq, fn))

    def pump(self):
        now = time.monotonic()
        while self._heap and self._heap[0][0] <= now:
            _w, _s, fn = heapq.heappop(self._heap)
            fn()

    def clear(self):
        self._heap.clear()


class DemoTransport:
    def __init__(self, engine, pattern_index: int = 0):
        self.engine = engine
        self.pattern = pattern_index
        self.running = False
        self.current_chord = 0
        self._sched = _Scheduler()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def toggle(self) -> bool:
        self.start() if not self.running else self.stop()
        return self.running

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop.set()
        self._sched.clear()
        self.engine.push("panic")

    def cycle_pattern(self, delta: int = 1):
        self.pattern = (self.pattern + delta) % len(PATTERNS)
        if self.running:
            self.restart()

    def restart(self):
        self._sched.clear()
        self._stop.set()
        self.running = False
        self.start()

    @property
    def pattern_name(self) -> str:
        return PATTERNS[self.pattern]["name"]

    @property
    def chord_name(self) -> str:
        info = PATTERNS[self.pattern]
        root = info["root"] + info["chords"][self.current_chord % len(info["chords"])]
        return _interval_name(root, info["spell"])

    # ---- sequencing ----------------------------------------------------
    def _run(self):
        while not self._stop.is_set():
            info = PATTERNS[self.pattern]
            self._step_loop(info)
            self._sleep(0.05)

    def _step_loop(self, info):
        beat = 60.0 / info["bpm"]
        bar = info["beats"] * beat
        t0 = time.monotonic()
        for gi in range(len(info["chords"])):
            if self._stop.is_set():
                return
            when = t0 + gi * bar
            self._sched.at(when, lambda gi=gi, info=info: self._play_chord(info, gi))
            if info["arp"] > 0.0:
                spell = SPELLS[info["spell"]]
                root = info["root"] + info["chords"][gi]
                notes = [root + s for s in spell]
                steps = info["beats"] * 2
                for s in range(steps):
                    self._sched.at(when + s * beat / 2.0,
                                   lambda s=s, notes=notes, beat=beat: self._play_arp(notes, s, beat))
            # run the scheduler or sleep
            while not self._stop.is_set():
                self._sched.pump()
                left = when + bar - time.monotonic()
                if left <= 0:
                    break
                self._sleep(0.01)
        self._sleep(bar)

    def _play_chord(self, info, gi: int):
        if self._stop.is_set():
            return
        root = info["root"] + info["chords"][gi]
        spell = SPELLS[info["spell"]]
        notes = [root + s for s in spell]
        dur = info["beats"] * 4 * (60.0 / info["bpm"])
        vel = 0.55 + 0.1 * (gi % 2)
        for n in notes:
            midi = n + _CENTRAL
            self.engine.push("note_on", midi, vel)
            self._sched.at(time.monotonic() + dur,
                           lambda midi=midi: self.engine.push("note_off", midi))

    def _play_arp(self, notes, step, beat):
        if self._stop.is_set():
            return
        n = notes[step % len(notes)] + _CENTRAL
        self.engine.push("note_on", n, 0.45)
        self._sched.at(time.monotonic() + beat * 0.4,
                       lambda n=n: self.engine.push("note_off", n))

    @staticmethod
    def _sleep(seconds):
        time.sleep(seconds)


def _interval_name(root: int, spell: str) -> str:
    octave = root // 12 - 1
    return f"{NOTE_NAMES[root % 12]}{octave}{_SPELL_LABEL.get(spell, '')}"