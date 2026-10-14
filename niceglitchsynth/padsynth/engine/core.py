"""AudioEngine - sounddevice output stream + event queue + meters.

The UI (or a MIDI thread or the demo transport) pushes event tuples into
``engine.push(event)``; the audio callback drains them just before rendering
the next block.
"""
from __future__ import annotations

import math
import queue
import time

from .fx import Chorus, Echo, MasterBus, Reverb
from .synth import BLOCK, SR, UNI_MAX, PolySynth

ERROR = ("error",)


def _drain(q, synth, ns):
    while True:
        try:
            ev = q.get_nowait()
        except queue.Empty:
            return
        kind = ev[0] if ev else ""
        if kind == "note_on":
            midi, vel = ev[1], ev[2]
            synth.note_on(midi + ns.transpose, vel)
            ns.note_count += 1
        elif kind == "note_off":
            midi = ev[1]
            synth.note_off(midi + ns.transpose)
            ns.note_count = max(0, ns.note_count - 1)
        elif kind == "sustain":
            synth.sustain_on() if ev[1] else synth.sustain_off()
        elif kind == "panic":
            synth.all_off()
            ns.note_count = 0
        elif kind == "transpose":
            ns.transpose = int(ev[1])


class AudioEngine:
    def __init__(self):
        self.p: dict = {}
        self.synth = PolySynth()
        self.synth.p = self.p
        self.chorus = Chorus(SR)
        self.chorus.p = self.p
        self.echo = Echo(SR)
        self.echo.p = self.p
        self.reverb = Reverb(SR)
        self.reverb.p = self.p
        self.master = MasterBus()
        self.master.p = self.p

        self.events: queue.Queue = queue.Queue()
        self.transpose = 0
        self.meter_l = 0.0
        self.meter_r = 0.0
        self.cpu = 0.0
        self.note_count = 0
        self._stream = None
        self.running = False
        self.last_error: str | None = None
        self.degrade = 0
        self._behind = 0
        self._easy = 0
        self._skip = False
        self._budget = BLOCK / SR

    def set_params(self, d: dict):
        """Swap in a new live parameter dict atomically."""
        self.p = d
        self.synth.p = d
        self.chorus.p = d
        self.echo.p = d
        self.reverb.p = d
        self.master.p = d

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=SR, blocksize=BLOCK, channels=2,
                dtype="float32", latency="low", callback=self._callback)
            self._stream.start()
            self.running = True
        except Exception as exc:  # pragma: no cover - device dependent
            self.running = False
            self.last_error = str(exc)

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.running = False

    # ---- events ---------------------------------------------------------
    def push(self, *ev):
        self.events.put(ev)

    def _drain_events(self):
        _drain(self.events, self.synth, self)

    # ---- audio ----------------------------------------------------------
    def _callback(self, outdata, frames, time_info, status):
        t0 = time.perf_counter()
        self._drain_events()
        busy = self.degrade
        if busy >= 4:
            self._skip = not self._skip
        if busy >= 4 and self._skip:
            outdata[:] = 0.0
            self.meter_l *= 0.4
            self.meter_r *= 0.4
            dt = time.perf_counter() - t0
            self.cpu = self.cpu * 0.9 + (dt / (BLOCK / SR)) * 0.1
            self._adapt(dt, status)
            return
        L, R = self.synth.render()
        if busy < 2:
            L, R = self.chorus.process(L, R)
            L, R = self.echo.process(L, R)
        if busy < 1:
            L, R = self.reverb.process(L, R)
        out = self.master.process(L, R)
        n = min(frames, len(out))
        outdata[:n, 0] = out[:n, 0]
        outdata[:n, 1] = out[:n, 1]
        rms = math.sqrt(float((out[:, 0] ** 2).mean()))
        self.meter_l = min(1.0, rms * 6.0)
        rms = math.sqrt(float((out[:, 1] ** 2).mean()))
        self.meter_r = min(1.0, rms * 6.0)
        dt = time.perf_counter() - t0
        self.cpu = self.cpu * 0.92 + (dt / (BLOCK / SR)) * 0.08
        self._adapt(dt, status)

    def _adapt(self, dt: float, status):
        """React to real-time pressure: raise/lower the degrade stage so the
        stream glitches but never dies."""
        budget = self._budget
        under = bool(getattr(status, "output_underflow", False)) if status else False
        if under or dt > budget * 1.1:
            self._behind += 3 if under else 1
            self._easy = 0
        else:
            self._behind = max(0, self._behind - 1)
            if dt < budget * 0.6:
                self._easy += 1
            else:
                self._easy = max(0, self._easy - 1)
        if self._behind >= 4 and self.degrade < 4:
            self.degrade += 1
            self._behind = 0
            self._apply_degrade()
        elif self._easy >= 12 and self.degrade > 0:
            self.degrade -= 1
            self._easy = 0
            self._apply_degrade()

    def _apply_degrade(self):
        d = self.degrade
        self.synth.max_unison = 2 if d >= 3 else UNI_MAX
        self.synth.aux_on = d < 3


class OfflineEngine:
    """No-audio engine: full synthesis chain rendered to RAM buffers.

    The TUI runs against this when no output device exists or ``--no-audio``
    is given; ``render(n)`` is also the test harness hook.
    """

    def __init__(self):
        self.p: dict = {}
        self.synth = PolySynth()
        self.chorus = Chorus(SR)
        self.echo = Echo(SR)
        self.reverb = Reverb(SR)
        self.master = MasterBus()
        self.set_params({})

        self.events: queue.Queue = queue.Queue()
        self.transpose = 0
        self.meter_l = 0.0
        self.meter_r = 0.0
        self.cpu = 0.0
        self.note_count = 0
        self.running = False
        self.last_error = "offline (no audio device / --no-audio)"
        self.degrade = 0

    def set_params(self, d: dict):
        self.p = d
        self.synth.p = d
        self.chorus.p = d
        self.echo.p = d
        self.reverb.p = d
        self.master.p = d

    def start(self):
        pass

    def stop(self):
        pass

    def push(self, *ev):
        self.events.put(ev)

    def _drain_events(self):
        _drain(self.events, self.synth, self)

    def sample_rate(self) -> int:
        return SR

    sr = property(sample_rate)

    def render(self, n: int) -> "np.ndarray":
        import numpy as np
        out = np.zeros((n, 2), dtype=np.float64)
        pos = 0
        while pos < n:
            self._drain_events()
            L, R = self.synth.render()
            L, R = self.chorus.process(L, R)
            L, R = self.echo.process(L, R)
            L, R = self.reverb.process(L, R)
            blk = self.master.process(L, R)
            k = min(len(blk), n - pos)
            out[pos:pos + k, 0] = blk[:k, 0]
            out[pos:pos + k, 1] = blk[:k, 1]
            pos += k
        return out


def make_engine(no_audio: bool = False) -> AudioEngine | OfflineEngine:
    if no_audio:
        return OfflineEngine()
    eng = AudioEngine()
    eng.start()
    if not eng.running and eng.last_error:
        off = OfflineEngine()
        off.last_error = f"audio unavailable: {eng.last_error}"
        return off
    return eng