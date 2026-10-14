"""PolySynth - the pad/string/air/ambience voice engine.

Numpy, block-based, vectorized. Live parameter values are read from a plain
dict (``self.p``) on every render call so the UI can mutate them freely.
"""
from __future__ import annotations

import math

import numpy as np

try:
    from scipy import signal  # fast biquad path
    _HAS_SCIPY = True
except Exception:  # pragma: no cover
    _HAS_SCIPY = False

SR = 44100
BLOCK = 256
WAVE_LEN = 512
UNI_MAX = 6
MAX_VOICES = 16

TAU = math.tau


def _make_wavetables() -> list[np.ndarray]:
    t = np.arange(WAVE_LEN) / WAVE_LEN
    sine = np.sin(TAU * t).astype(np.float32)
    tri = (2 / np.pi) * np.arcsin(np.sin(TAU * t)).astype(np.float32)
    saw = np.zeros(WAVE_LEN, np.float32)
    saw[: WAVE_LEN // 2] = np.linspace(0.0, 1.0, WAVE_LEN // 2, endpoint=False, dtype=np.float32)
    saw[WAVE_LEN // 2:] = np.linspace(-1.0, 1.0, WAVE_LEN // 2, endpoint=False, dtype=np.float32)
    squ = np.where(t < 0.5, 1.0, -1.0).astype(np.float32)
    return [sine, tri, saw, squ]


_TABLES = _make_wavetables()


class ADSR:
    """Envelope with vectorized chunk fills. Stages advance per sample but are
    computed in numpy chunks whenever a stage spans many samples."""

    IDLE, ATK, DEC, SUS, REL, OFF = range(6)

    def __init__(self, peak: float = 1.0):
        self.state = self.IDLE
        self.level = 0.0
        self.peak = peak
        self.a = self.d = self.s = self.r = 0.0
        self.atk_tgt = peak

    def note_on(self, a, d, s, r, peak: float):
        self.a, self.d, self.s, self.r = max(a, 0.0002), max(d, 0.0002), s, r
        self.peak = peak
        self.atk_tgt = peak
        self.state = self.ATK if peak > 0.0 else self.OFF
        self.level = 0.0

    def note_off(self):
        if self.state in (self.ATK, self.DEC, self.SUS):
            self.state = self.REL

    def _coeff(self, t: float) -> float:
        return 1.0 - math.exp(-1.0 / (t * SR))

    def render(self, n: int) -> np.ndarray:
        out = np.empty(n, dtype=np.float32)
        pos = 0
        while pos < n:
            rem = n - pos
            st = self.state
            if st == self.ATK:
                c = self._coeff(self.a * 0.4)
                seg = self._seg_approach(rem, st, c, self.atk_tgt)
                c_vec = (1.0 - c) ** np.arange(1, seg + 1, dtype=np.float32)
                out[pos:pos + seg] = self.atk_tgt + (self.level - self.atk_tgt) * c_vec
                self.level = float(out[pos + seg - 1])
                if abs(self.level - self.atk_tgt) < 0.0005 or self.a < 0.002:
                    self._to_decay()
                pos += seg
            elif st == self.DEC:
                c = self._coeff(self.d)
                target_sus = self.atk_tgt * self.s
                seg = self._seg_approach(rem, st, c, target_sus)
                c_vec = (1.0 - c) ** np.arange(1, seg + 1, dtype=np.float32)
                out[pos:pos + seg] = target_sus + (self.level - target_sus) * c_vec
                self.level = float(out[pos + seg - 1])
                if abs(self.level - target_sus) < 0.0005 or self.s >= 0.999:
                    self.level = target_sus
                    self.state = self.SUS
                pos += seg
            elif st == self.SUS:
                self.level = self.atk_tgt * self.s
                out[pos:] = self.level
                pos = n
            elif st == self.REL:
                c = self._coeff(self.r)
                seg = self._seg_approach(rem, st, c, 0.0)
                c_vec = (1.0 - c) ** np.arange(1, seg + 1, dtype=np.float32)
                out[pos:pos + seg] = self.level * c_vec
                self.level = float(out[pos + seg - 1])
                if self.level < 0.0002:
                    self.level = 0.0
                    self.state = self.OFF
                pos += seg
            else:
                out[pos:] = 0.0
                pos = n
        return out

    def _seg_approach(self, rem: int, st: int, c: float, target: float) -> int:
        """How many samples of this monotone approach can we emit this block?"""
        if st == self.ATK:
            need = min(rem, max(1, math.ceil(self.a * 0.4 * SR)))
            return need
        if st == self.DEC:
            need = min(rem, max(1, math.ceil(self.d * SR)))
            return need
        if st == self.REL:
            need = min(rem, max(1, math.ceil(self.r * SR)))
            return need
        return rem

    def _to_decay(self):
        self.state = self.DEC


class Biquad:
    """Per-voice 2nd-order filter with persistent state."""

    __slots__ = ("z1", "z2")

    def __init__(self):
        self.z1 = 0.0
        self.z2 = 0.0

    def process(self, x: np.ndarray, fc: float, q: float, mode: int) -> np.ndarray:
        w0 = math.tau * max(1.0, float(fc)) / SR
        cosw = math.cos(w0)
        alpha = math.sin(w0) / (2.0 * max(q, 0.2))
        a0 = 1.0 + alpha
        a1 = -2.0 * cosw / a0
        a2 = (1.0 - alpha) / a0
        if mode == 0:
            b = ((1.0 - cosw) / 2.0, 1.0 - cosw, (1.0 - cosw) / 2.0)
        elif mode == 1:
            b = (alpha, 0.0, -alpha)
        else:
            b = ((1.0 + cosw) / 2.0, -(1.0 + cosw), (1.0 + cosw) / 2.0)
        b = tuple(v / a0 for v in b)

        if _HAS_SCIPY:
            y, zf = signal.lfilter(b, (1.0, a1, a2), x, zi=np.array([self.z1, self.z2], np.float64))
            self.z1, self.z2 = float(zf[0]), float(zf[1])
            return np.ascontiguousarray(y, dtype=np.float32)

        out = np.empty(x.size, dtype=np.float32)
        z1, z2 = self.z1, self.z2
        b0, b1, b2 = b
        for i in range(x.size):
            xi = x[i]
            y = b0 * xi + z1
            z1 = b1 * xi - a1 * y + z2
            z2 = b2 * xi - a2 * y
            out[i] = y
        self.z1, self.z2 = z1, z2
        return out


class Voice:
    __slots__ = ("active", "note", "midi", "vel", "pan", "u_phase", "sphase",
                 "amp_env", "flt_env", "l1p", "l2p", "held", "filter", "seq")

    def __init__(self):
        self.active = False
        self.note = 0.0
        self.midi = 60
        self.vel = 1.0
        self.pan = 0.0
        self.u_phase = np.zeros(UNI_MAX, dtype=np.float32)
        self.sphase = 0.0
        self.amp_env = ADSR()
        self.flt_env = ADSR(peak=1.0)
        self.l1p = 0.0
        self.l2p = 0.0
        self.held = False
        self.filter = Biquad()
        self.seq = 0


class PolySynth:
    def __init__(self):
        self.p: dict = {}
        self.sustain = False
        self.voices: list[Voice] = [Voice() for _ in range(MAX_VOICES)]
        self._gen = 0
        self._noise = np.zeros(BLOCK, dtype=np.float32)
        self._buf_l = np.zeros(BLOCK, dtype=np.float32)
        self._buf_r = np.zeros(BLOCK, dtype=np.float32)

    # ---- events --------------------------------------------------------
    def note_on(self, midi: int, vel: float = 0.8):
        v = self._acquire()
        if v is None:
            return
        v.active = True
        v.held = False
        self._gen += 1
        v.seq = self._gen
        v.midi = midi
        v.vel = max(0.0, min(1.0, vel))
        p = self.p
        semis = p.get("osc.semis", 0.0)
        fine = p.get("osc.fine", 0.0)
        v.note = midi + semis + fine / 100.0
        panb = p.get("pan.base", 0.0)
        sprd = p.get("pan.spread", 0.5)
        v.pan = max(-1.0, min(1.0, panb + (np.random.random() - 0.5) * sprd * 2.0))
        v.l1p = np.random.random()
        v.l2p = np.random.random()
        v.u_phase[:] = np.random.random(UNI_MAX)
        v.sphase = 0.0
        vsens = p.get("amp.vel", 0.5)
        peak = 1.0 - vsens * (1.0 - v.vel)
        v.amp_env.note_on(p.get("amp.a", 0.05), p.get("amp.d", 0.5),
                          p.get("amp.s", 0.7), p.get("amp.r", 1.0), peak)
        v.flt_env.note_on(p.get("flt.a", 0.05), p.get("flt.d", 0.5),
                          p.get("flt.s", 0.4), p.get("flt.r", 1.0), 1.0)
        v.filter = Biquad()

    def note_off(self, midi: int):
        for v in self.voices:
            if v.active and not v.held and int(round(v.midi)) == midi:
                if self.sustain:
                    v.held = True
                else:
                    v.amp_env.note_off()
                    v.flt_env.note_off()
                break

    def sustain_on(self):
        self.sustain = True

    def sustain_off(self):
        self.sustain = False
        for v in self.voices:
            if v.held:
                v.held = False
                v.amp_env.note_off()
                v.flt_env.note_off()

    def all_off(self):
        for v in self.voices:
            v.held = False
            v.amp_env.note_off()
            v.flt_env.note_off()

    def _acquire(self) -> Voice:
        for v in self.voices:
            if not v.active:
                return v
        oldest = min(self.voices, key=lambda v: v.seq)
        oldest.amp_env.note_off()
        oldest.flt_env.note_off()
        return oldest

    # ---- rendering -----------------------------------------------------
    def render(self) -> tuple[np.ndarray, np.ndarray]:
        L = self._buf_l
        R = self._buf_r
        L[:] = 0.0
        R[:] = 0.0
        p = self.p
        if not p:
            return L, R
        self._noise = np.random.randn(BLOCK).astype(np.float32)

        for v in self.voices:
            if not v.active:
                continue
            self._render_voice(v, L, R)
            if v.amp_env.state == ADSR.OFF:
                v.active = False
        return L, R

    def _blend_wave(self, wave: float) -> np.ndarray:
        stage = max(0.0, min(0.9999, wave)) * 3.0
        i = int(stage)
        f = stage - i
        return (1.0 - f) * _TABLES[i] + f * _TABLES[i + 1]

    def _render_voice(self, v: Voice, L: np.ndarray, R: np.ndarray):
        p = self.p
        freq = 440.0 * 2.0 ** ((v.note - 69) / 12.0)

        # --- LFOs -------------------------------------------------------
        l1p = v.l1p
        l1r = p["l1.rate"] / SR
        l1 = _lfo_wave(l1p, l1r, int(p["l1.wave"]), BLOCK)
        v.l1p = (l1p + l1r * BLOCK) % 1.0
        l2p = v.l2p
        l2r = p["l2.rate"] / SR
        l2 = _lfo_wave(l2p, l2r, int(p["l2.wave"]), BLOCK)
        v.l2p = (l2p + l2r * BLOCK) % 1.0

        pitch_l1 = (l1 * (p["l1.dep"] * 2.0) * (1.0 if int(p["l1.tgt"]) == 0 else 0.0))
        pitch_l2 = (l2 * (p["l2.dep"] * 2.0) * (1.0 if int(p["l2.tgt"]) == 0 else 0.0))
        freq = freq * 2.0 ** (pitch_l1 / 12.0) * 2.0 ** (pitch_l2 / 12.0)

        # --- envelope ---------------------------------------------------
        amp = v.amp_env.render(BLOCK)
        fenv = v.flt_env.render(BLOCK)
        lvl_lfo = 1.0 - (l1 * p["l1.dep"] * 0.6 * (int(p["l1.tgt"]) == 3))
        lvl_lfo = lvl_lfo * (1.0 - (l2 * p["l2.dep"] * 0.6 * (int(p["l2.tgt"]) == 3)))
        amp = amp * lvl_lfo

        # --- oscillator sum ----------------------------------------------
        U = int(round(p["osc.unison"]))
        U = max(1, min(UNI_MAX, U))
        det = p["osc.detune"]
        weight = np.empty(U, np.float32)
        mult = np.empty(U, np.float32)
        for u in range(U):
            off = (u - (U - 1) / 2.0) * det
            mult[u] = 2.0 ** (off / 1200.0)
            weight[u] = 1.0 / U
        inc = np.outer(mult, freq / SR).astype(np.float32)  # (U, n)
        t = np.arange(BLOCK)
        phases = v.u_phase[:U][:, None] + np.cumsum(inc, axis=1) - inc
        phases = phases - np.floor(phases)

        wt = self._blend_wave(p["osc.wave"])
        idx_f = phases * WAVE_LEN
        i0 = idx_f.astype(np.int32) % WAVE_LEN
        frac = idx_f - np.floor(idx_f)
        i1 = (i0 + 1) % WAVE_LEN
        osc = (wt[i0] * (1.0 - frac) + wt[i1] * frac) * weight[:, None]
        mix = osc.sum(axis=0).astype(np.float32)
        v.u_phase[:U] = phases[:, -1] % 1.0

        sub = p["osc.sub"]
        if sub > 0.0:
            subinc = freq.mean() * 0.5 / SR
            sp = v.sphase + np.cumsum(np.full(BLOCK, subinc, np.float32)) - subinc
            sp = sp - np.floor(sp)
            v.sphase = (v.sphase + subinc * BLOCK) % 1.0
            mix = mix + np.sin(TAU * sp) * sub

        noise = p["osc.noise"]
        if noise > 0.0:
            mix = mix + self._noise * noise * 0.5

        in_sig = mix

        # --- filter -------------------------------------------------------
        base_cut = p["filter.cut"]
        keym = p["filter.key"]
        keynote = v.midi
        cut = base_cut * 2.0 ** (keym * (keynote - 69) / 12.0)
        famt = p["flt.amt"]
        env_mult = 2.0 ** (fenv * famt * 4.0)
        cut = cut * env_mult
        flfo = int(p["l1.tgt"]) == 1
        flfo2 = int(p["l2.tgt"]) == 1
        cut = (cut * 2.0 ** (l1 * (p["l1.dep"] * 3.0) * flfo)
               * 2.0 ** (l2 * (p["l2.dep"] * 3.0) * flfo2))
        cut = np.clip(cut, 20.0, SR * 0.45)
        mode = int(round(p["filter.mode"]))
        res = p["filter.res"]
        q = max(0.3, 0.5 + res * 7.0)
        in_sig = v.filter.process(in_sig, float(cut.mean()), q, mode)

        out = in_sig * amp
        pan_a = 0.5 * (1.0 + v.pan)
        gl = math.cos(pan_a * math.pi / 2.0)
        gr = math.sin(pan_a * math.pi / 2.0)
        L += out * gl
        R += out * gr


def _lfo_wave(phase: float, rate: float, kind: int, n: int) -> np.ndarray:
    ph = phase + rate * np.arange(n)
    ph = ph - np.floor(ph)
    if kind == 0:
        return np.sin(TAU * ph).astype(np.float32)
    if kind == 1:
        return ((4.0 * ph) % 2.0 - 1.0).astype(np.float32)
    if kind == 2:
        return np.where(ph < 0.5, 1.0, -1.0).astype(np.float32)
    return (np.random.random(n) * 2.0 - 1.0).astype(np.float32)