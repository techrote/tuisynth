"""Patch architecture: parameter registry, A/B morph, macros, presets.

A Patch is a plain dict of float values keyed by ``PARAM`` keys, plus an
optional ``b`` dict (morph target) and ``macros`` (single-param offsets).

The live value for a param is::

    base = lerp(a, b, morph)      (discrete params snap to the dominant side)
    live = clamp(base + macro_delta, lo, hi)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .util import clamp

PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    lo: float
    hi: float
    default: float = 0.0
    log: bool = False
    discrete: bool = False
    unit: str = ""
    fmt: Callable[[float], str] | None = None
    group: str = "voice"


PARAMS: list[ParamSpec] = [
    # ---- voice / oscillator
    ParamSpec("osc.wave", "WAVE", 0.0, 1.0, 0.55, fmt=lambda v: f"{v:.2f}"),
    ParamSpec("osc.unison", "UNIS", 1.0, 6.0, 2.0, discrete=True, fmt=lambda v: f"{int(round(v))}"),
    ParamSpec("osc.detune", "DETN", 0.0, 40.0, 8.0, unit="ct", fmt=lambda v: f"{v:.1f}ct"),
    ParamSpec("osc.semis", "SEMI", -24.0, 24.0, 0.0, discrete=True, fmt=lambda v: f"{int(round(v))}"),
    ParamSpec("osc.fine", "FINE", -99.0, 99.0, 0.0, discrete=True, fmt=lambda v: f"{int(round(v))}"),
    ParamSpec("osc.sub", "SUBL", 0.0, 1.0, 0.0, fmt=lambda v: f"{v:.2f}"),
    ParamSpec("osc.noise", "NOIS", 0.0, 1.0, 0.0, fmt=lambda v: f"{v:.2f}"),
    # ---- filter
    ParamSpec("filter.mode", "MODE", 0.0, 2.0, 0.0, discrete=True,
              fmt=lambda v: ("LP", "BP", "HP")[int(round(v))]),
    ParamSpec("filter.cut", "CUT", 40.0, 16000.0, 2400.0, log=True, unit="hz"),
    ParamSpec("filter.res", "RES", 0.0, 1.0, 0.15, fmt=lambda v: f"{v:.2f}"),
    ParamSpec("filter.envd", "ENVD", 0.0, 1.0, 0.35, fmt=lambda v: f"{v:.2f}"),
    ParamSpec("filter.key", "KEYT", 0.0, 1.0, 0.4, fmt=lambda v: f"{v:.2f}"),
    # ---- amp envelope
    ParamSpec("amp.a", "ATK", 0.001, 9.0, 1.2, log=True, unit="s"),
    ParamSpec("amp.d", "DEC", 0.01, 9.0, 1.0, log=True, unit="s"),
    ParamSpec("amp.s", "SUS", 0.0, 1.0, 0.85, fmt=lambda v: f"{int(round(v * 100))}%"),
    ParamSpec("amp.r", "REL", 0.02, 12.0, 3.0, log=True, unit="s"),
    ParamSpec("amp.vel", "VELC", 0.0, 1.0, 0.5, fmt=lambda v: f"{v:.2f}"),
    # ---- filter envelope
    ParamSpec("flt.a", "FATK", 0.001, 9.0, 1.5, log=True, unit="s"),
    ParamSpec("flt.d", "FDEC", 0.01, 9.0, 1.4, log=True, unit="s"),
    ParamSpec("flt.s", "FSUS", 0.0, 1.0, 0.5, fmt=lambda v: f"{int(round(v * 100))}%"),
    ParamSpec("flt.r", "FREL", 0.02, 12.0, 3.5, log=True, unit="s"),
    ParamSpec("flt.amt", "FAMT", -1.0, 1.0, 0.4),
    # ---- lfo 1 / 2
    ParamSpec("l1.rate", "L1RAW", 0.02, 8.0, 0.25, log=True, unit="hz"),
    ParamSpec("l1.wave", "L1WAV", 0.0, 3.0, 0.0, discrete=True,
              fmt=lambda v: ("SIN", "TRI", "SQR", "RND")[int(round(v))]),
    ParamSpec("l1.tgt", "L1TGT", 0.0, 3.0, 0.0, discrete=True,
              fmt=lambda v: ("PIT", "CUT", "PAN", "LVL")[int(round(v))]),
    ParamSpec("l1.dep", "L1DEP", 0.0, 1.0, 0.15, fmt=lambda v: f"{v:.2f}"),
    ParamSpec("l2.rate", "L2RAW", 0.02, 8.0, 0.4, log=True, unit="hz"),
    ParamSpec("l2.wave", "L2WAV", 0.0, 3.0, 1.0, discrete=True,
              fmt=lambda v: ("SIN", "TRI", "SQR", "RND")[int(round(v))]),
    ParamSpec("l2.tgt", "L2TGT", 0.0, 3.0, 1.0, discrete=True,
              fmt=lambda v: ("PIT", "CUT", "PAN", "LVL")[int(round(v))]),
    ParamSpec("l2.dep", "L2DEP", 0.0, 1.0, 0.10, fmt=lambda v: f"{v:.2f}"),
    # ---- pan
    ParamSpec("pan.base", "PANB", -1.0, 1.0, 0.0, fmt=lambda v: f"{v:+.2f}"),
    ParamSpec("pan.spread", "PANS", 0.0, 1.0, 0.5, fmt=lambda v: f"{v:.2f}"),
    # ---- fx
    ParamSpec("fx.chorus.mix", "CMIX", 0.0, 1.0, 0.0, group="fx"),
    ParamSpec("fx.chorus.rate", "CRAT", 0.1, 6.0, 1.0, log=True, unit="hz", group="fx"),
    ParamSpec("fx.chorus.depth", "CDEP", 0.0, 0.02, 0.004, unit="s", group="fx"),
    ParamSpec("fx.delay.time", "DLYT", 0.06, 2.0, 0.45, log=True, unit="s", group="fx"),
    ParamSpec("fx.delay.fb", "DFBK", 0.0, 0.9, 0.25, fmt=lambda v: f"{v:.2f}", group="fx"),
    ParamSpec("fx.delay.mix", "DMIX", 0.0, 1.0, 0.0, group="fx"),
    ParamSpec("fx.reverb.size", "RVSZ", 0.2, 1.6, 1.0, fmt=lambda v: f"{v:.2f}", group="fx"),
    ParamSpec("fx.reverb.damp", "RVDP", 0.0, 0.9, 0.35, fmt=lambda v: f"{v:.2f}", group="fx"),
    ParamSpec("fx.reverb.mix", "RVMX", 0.0, 1.0, 0.35, group="fx"),
    # ---- master
    ParamSpec("master.level", "LVLS", 0.0, 1.0, 0.8, group="mix"),
    ParamSpec("master.drive", "DRVE", 0.0, 1.0, 0.15, group="mix"),
]

BY_KEY: dict[str, ParamSpec] = {p.key: p for p in PARAMS}

GROUPS: list[tuple[str, str]] = [
    ("voice", "VOICE/OSC"),
    ("filter", "FILTER"),
    ("env", "ENVELOPE"),
    ("lfo", "LFO"),
    ("pan", "PAN"),
    ("fx", "FX"),
    ("mix", "MASTER"),
]

_GROUP_MAP = {
    "voice": "voice", "filter": "filter", "env": "env", "lfo": "lfo", "pan": "pan",
    "fx": "fx", "mix": "mix",
}


def spec(key: str) -> ParamSpec:
    return BY_KEY[key]


def default_patch() -> dict:
    return {p.key: p.default for p in PARAMS}


def lerp(a: float, b: float, m: float) -> float:
    return a + (b - a) * m


def morph_live(a: dict, b: dict, morph: float) -> dict:
    """Blend A/B into a live value dict, applying per-param clamps."""
    out: dict = {}
    for p in PARAMS:
        va = a.get(p.key, p.default)
        vb = b.get(p.key, p.default)
        v = vb if (p.discrete and morph > 0.5) else lerp(va, vb, morph)
        out[p.key] = float(clamp(v, p.lo, p.hi))
    return out


def apply_macros(live: dict, macros: dict, macro_values: list[float]) -> dict:
    """macros: {key: scale}; macro_values[-1..1]; additive, clamped."""
    if not macros:
        return live
    out = dict(live)
    for idx, (key, scale) in enumerate(macros.items()):
        if idx >= len(macro_values) or not scale:
            continue
        p = BY_KEY.get(key)
        if p is None:
            continue
        out[key] = float(clamp(out[key] + macro_values[idx] * scale, p.lo, p.hi))
    return out


def group_of(key: str) -> str:
    p = BY_KEY.get(key)
    return _GROUP_MAP.get(p.group if p else "fx", "voice")


class Patch:
    def __init__(self, name: str = "untitled", char: str = "pad",
                 a: dict | None = None, b: dict | None = None,
                 macros: dict | None = None, morph: float = 0.0):
        self.name = name
        self.char = char
        self.a = default_patch() if a is None else {**default_patch(), **a}
        self.b = default_patch() if b is None else {**default_patch(), **b}
        self.macros: dict = dict(macros) if macros else {}
        self.morph = float(morph)

    def live(self, macro_values=None) -> dict:
        live = morph_live(self.a, self.b, self.morph)
        if macro_values:
            live = apply_macros(live, self.macros, macro_values)
        return live

    def set_a(self, key: str, value: float):
        p = BY_KEY[key]
        self.a[key] = float(clamp(value, p.lo, p.hi))

    def set_b(self, key: str, value: float):
        p = BY_KEY[key]
        self.b[key] = float(clamp(value, p.lo, p.hi))

    def touch(self, key: str, value: float):
        """Write to both A and B so morph never fights the last edit."""
        self.set_a(key, value)
        self.set_b(key, value)

    def to_dict(self) -> dict:
        return {"name": self.name, "char": self.char, "morph": self.morph,
                "a": self.a, "b": self.b, "macros": self.macros}

    @classmethod
    def from_dict(cls, d: dict) -> "Patch":
        return cls(name=d.get("name", "untitled"), char=d.get("char", "pad"),
                   a=d.get("a"), b=d.get("b"), macros=d.get("macros"),
                   morph=d.get("morph", 0.0))


def load_preset(path: Path) -> Patch:
    return Patch.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_preset(patch: Patch, path: Path):
    path.write_text(json.dumps(patch.to_dict(), indent=2), encoding="utf-8")


def list_presets() -> list[Path]:
    if not PRESETS_DIR.exists():
        return []
    return sorted(PRESETS_DIR.glob("*.json"))