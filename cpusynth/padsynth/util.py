"""Shared helpers: note math, formatting, small utilities."""
from __future__ import annotations

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_name(note: int) -> str:
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


def midi_to_freq(note: float) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def fmt_hz(v: float) -> str:
    if v >= 1000:
        return f"{v / 1000:.2f}k"
    return f"{v:.0f}"


def fmt_time(v: float) -> str:
    if v >= 1:
        return f"{v:.2f}s"
    return f"{v * 1000:.0f}ms"


def fmt_pct(v: float) -> str:
    return f"{int(round(v * 100)):>3}%"


def fmt_cents(v: float) -> str:
    return f"{v:+.0f}ct"


def fmt_int(v: float) -> str:
    return f"{int(round(v))}"