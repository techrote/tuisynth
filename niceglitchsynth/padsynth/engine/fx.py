"""FX chain: chorus, ping-pong delay, Schroeder reverb, limiter/dc-block.

All DSP is numpy, block-based. Each unit keeps its own state and exposes a
``process(L, R)`` that reads live parameter values from a plain dict on every
call (``self.p.get(key, default)``).
"""
from __future__ import annotations

import numpy as np

from .synth import BLOCK

_AI = np.arange(BLOCK)


class DelayLine:
    __slots__ = ("buf", "l", "wp")

    def __init__(self, length: int):
        self.buf = np.zeros(max(1, length), dtype=np.float32)
        self.l = self.buf.size
        self.wp = 0

    def read(self, n: int, delay: int) -> np.ndarray:
        idx = (self.wp - int(delay) - (_AI if n == BLOCK else np.arange(n))) % self.l
        return self.buf[idx]

    def write(self, chunk: np.ndarray):
        n = chunk.size
        idx = (self.wp + (_AI if n == BLOCK else np.arange(n))) % self.l
        self.buf[idx] = chunk
        self.wp = (self.wp + n) % self.l

    def read_write(self, chunk: np.ndarray, delay: int) -> np.ndarray:
        out = self.read(chunk.size, delay)
        self.write(chunk)
        return out


class OnePole:
    """First-order smoothing. Vectorized as ``y[i] = b**i * y0 + sum`` so a
    whole block costs one exp + one cumsum; no per-sample Python."""
    __slots__ = ("y",)

    def __init__(self, init: float = 0.0):
        self.y = float(init)

    def process(self, x: np.ndarray, alpha: float) -> np.ndarray:
        a = min(1.0, max(0.0, float(alpha)))
        if a <= 0.0:
            return np.zeros_like(x)
        if a >= 1.0:
            self.y = float(x[-1])
            return np.ascontiguousarray(x, dtype=np.float32)
        b = 1.0 - a
        n = x.size
        if b < 0.06:  # b**-n would overflow; fall back to the loop path
            out = np.empty_like(x)
            y = self.y
            for i in range(n):
                y += a * (x[i] - y)
                out[i] = y
            self.y = y
            return out
        i = _AI[:n] if n == BLOCK else np.arange(n)
        s = np.log(b)
        b_i = np.exp(s * i)
        inv = np.exp(-s * i)
        xi = np.asarray(x, dtype=np.float64)
        y = b * b_i * self.y + a * b_i * np.cumsum(xi * inv)
        self.y = float(y[-1])
        return np.ascontiguousarray(y, dtype=np.float32)


class Chorus:
    def __init__(self, sr: int):
        self.p: dict = {}
        self.sr = sr
        self._l = DelayLine(int(sr * 0.045))
        self._r = DelayLine(int(sr * 0.045))
        self._ph1 = 0.0
        self._ph2 = 2.2  # offset LFO phase between channels

    def process(self, L: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mix = float(self.p.get("fx.chorus.mix", 0.0))
        if mix <= 0.0:
            return L, R
        rate = float(self.p.get("fx.chorus.rate", 1.0))
        depth = float(self.p.get("fx.chorus.depth", 0.004))
        rate /= self.sr
        n = L.size

        ph1 = self._ph1 + rate * n
        ph2 = self._ph2 + rate * n
        self._ph1 = ph1 % 1.0
        self._ph2 = ph2 % 1.0

        base = int(self.sr * 0.009)
        spread = int(depth * self.sr * 0.5)
        ai = _AI if n == BLOCK else np.arange(n)
        d1 = (np.sin(2 * np.pi * (ph1 / n * ai)) * spread).astype(np.int32) + base
        d2 = (np.sin(2 * np.pi * (ph2 / n * ai) + 1.1) * spread).astype(np.int32) + base

        wl = self._l.read_write(L, int(d1[0]))
        wr = self._r.read_write(R, int(d2[0]))
        dl = _vshift_delay(wl, d1)
        dr = _vshift_delay(wr, d2)
        return L + mix * dl, R + mix * dr


def _vshift_delay(sig: np.ndarray, delays: np.ndarray) -> np.ndarray:
    """Apply per-sample integer delays via a gather."""
    n = sig.size
    ai = _AI[:n] if n == BLOCK else np.arange(n)
    idx = ai - np.clip(delays.astype(np.int32), 0, n - 1)
    idx = np.maximum(idx, 0)
    return np.ascontiguousarray(sig[idx], dtype=np.float32)


class Echo:
    def __init__(self, sr: int):
        self.p: dict = {}
        self.sr = sr
        self._l = DelayLine(int(sr * 2.2))
        self._r = DelayLine(int(sr * 2.2))

    def process(self, L: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        dly = self.p.get("fx.delay.time", 0.45)
        fb = self.p.get("fx.delay.fb", 0.2)
        mix = self.p.get("fx.delay.mix", 0.0)
        if mix <= 0.0:
            return L, R
        n = L.size
        taps = int(dly * self.sr)
        dl = self._l.read(n, taps)
        dr = self._r.read(n, taps)
        l_in = L + fb * dl
        r_in = R + fb * dr
        self._l.write(l_in)
        self._r.write(r_in)
        # cross-feed ping-pong: R echoes the left tap, L echoes the right
        return L + mix * dl + 0.3 * mix * dr, R + mix * dr + 0.3 * mix * dl


class Reverb:
    """Schroeder reverb: 2x4 combs + 2 allpass, stereo decorrelated."""

    COMB = [1177, 1273, 1427, 1559]
    AP = [137, 199]

    def __init__(self, sr: int):
        self.p: dict = {}
        self.sr = sr
        self._lines: list[tuple[DelayLine, OnePole]] = []
        self._aps: list[DelayLine] = []
        for ch in range(2):
            sc = 1.618 if ch else 1.0
            for base in self.COMB:
                taps = max(8, int(base * sc))
                self._lines.append((DelayLine(taps + 1024), OnePole()))
            for ap in self.AP:
                taps = max(8, int(ap * sc))
                self._aps.append(DelayLine(taps + 1024))
        self._ncombs = len(self.COMB)

    def process(self, L: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mix = self.p.get("fx.reverb.mix", 0.0)
        if mix <= 0.0:
            return L, R
        size = float(self.p.get("fx.reverb.size", 1.0))
        damp = float(self.p.get("fx.reverb.damp", 0.35))
        n = L.size
        wet = np.zeros((2, n), dtype=np.float32)

        for ch, sig in enumerate((L, R)):
            sc = size * (1.618 if ch else 1.0)
            li0 = ch * self._ncombs
            ai0 = ch * len(self.AP)
            acc = np.zeros(n, dtype=np.float32)
            for i, base in enumerate(self.COMB):
                line, pole = self._lines[li0 + i]
                taps = max(8, int(base * sc))
                read = line.read(n, taps)
                damped = pole.process(read, damp * 0.25)
                fb = 0.83 - 0.04 * i
                out = sig + fb * damped
                line.write(out)
                acc += read
            acc = acc / self._ncombs
            for j, ap in enumerate(self.AP):
                line = self._aps[ai0 + j]
                taps = max(8, int(ap * sc))
                a_in = acc + 0.5 * line.read(n, taps)
                line.write(a_in)
                acc = -0.5 * a_in + line.read(n, taps)
            wet[ch] = acc

        return L + mix * wet[0], R + mix * wet[1]


class MasterBus:
    def __init__(self):
        self.p: dict = {}
        self._dc_l = OnePole()
        self._dc_r = OnePole()

    def process(self, L: np.ndarray, R: np.ndarray) -> np.ndarray:
        drive = float(self.p.get("master.drive", 0.0)) * 8.0 + 1.0
        level = float(self.p.get("master.level", 0.8))
        L = np.tanh(drive * L) * level
        R = np.tanh(drive * R) * level
        # gentle DC blocker (one-pole highpass ~ 20Hz)
        alpha = 0.004
        L = L - self._dc_l.process(L, alpha)
        R = R - self._dc_r.process(R, alpha)
        return np.column_stack((L, R))