"""padsynth entry point: python -m padsynth [--theme NAME] [--no-audio]
[--midi INDEX] [PATCH.json]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .param import default_patch, load_preset, list_presets, Patch


def build_patch(path: str | None) -> Patch:
    if path:
        p = Path(path)
        if not p.exists():
            p = Path(__file__).resolve().parent.parent / "presets" / f"{path}.json"
        if not p.exists():
            raise SystemExit(f"patch not found: {path}")
        return load_preset(p)
    presets = list_presets()
    if presets:
        return load_preset(presets[0])
    return Patch(name="untitled", char="pad")


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(prog="padsynth", description="mouse-first terminal synthesizer")
    ap.add_argument("--theme", default=None, help="theme/skin name or path (themes/*.toml)")
    ap.add_argument("--no-audio", action="store_true", help="run the UI without an audio device")
    ap.add_argument("--midi", type=int, default=None, help="MIDI-in port index (0 = first) for rtmidi")
    ap.add_argument("patch", nargs="?", default=None, help="preset file to load (presets/*.json)")
    args = ap.parse_args(argv)

    try:
        from .themes import load_any_theme
        skin = load_any_theme(args.theme)
    except Exception as exc:
        print(f"[padsynth] theme error: {exc}", file=sys.stderr)
        return 1
    for w in skin.warnings:
        print(f"[padsynth] skin note: {w}", file=sys.stderr)

    from .engine import make_engine
    engine = make_engine(args.no_audio)

    patch = build_patch(args.patch)

    from .midi import MidiInput
    midi = MidiInput(engine)
    if args.midi is not None and midi.available():
        ok = midi.open(args.midi)
        if not ok:
            print(f"[padsynth] MIDI open failed: {midi.error}", file=sys.stderr)

    from .demo import DemoTransport
    demo = DemoTransport(engine)

    from .ui import PadSynthApp
    app = PadSynthApp(engine, patch, skin, midi, demo, args)
    app.run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)