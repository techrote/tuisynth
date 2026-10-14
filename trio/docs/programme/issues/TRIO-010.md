# [TRIO-010] AURORA app: harmonic painter and aurora waterfall

Work in `techrote/tuisynth` on **TRIO-010** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-008 (#9) and TRIO-009 (#10) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/06-AURORA-SPEC.md` section "UI" and the UI items under "Tests"
4. `trio/docs/rag/00-CHARTER.md` (AURORA column and difference contract)
5. `trio/docs/rag/04-TUI-UX-CONTRACT.md` sections "Philosophy", "App shell"
6. `trio/docs/rag/05-SKINS-CONTRACT.md` sections "Format", "Required roles",
   "Per-instrument factory colourways"
7. The kit demo instrument `trio/kit/src/trio_kit/demo.py` as the integration example

## Objective

A playable, beautiful AURORA: tabbed screens, harmonic painter, live aurora waterfall,
full-width on-screen piano, four skins and the shared CLI, so `aurora` starts a working synth.

## Files (under `trio/aurora/src/trio_aurora/`)

- `widgets.py`: `HarmonicPainter` (64/32 bars, drag paint with path interpolation, right-drag
  erase, wheel, keyboard twin incl. `Ctrl+R`, `Ctrl+E`, `Ctrl+O`; each change is sent as
  `InstrumentEvent("harmonics", tuple_of_64_floats)`, which `AuroraInstrument.on_event`
  validates and hands to the regenerator; the painted profile is saved in presets as
  `extras.harmonics`) and `AuroraWaterfall` (scrolling rows from telemetry
  `spectrum`, skin `density` glyphs and `aurora` ramp, frozen in snapshot mode).
- `ui.py`: `make_layout(shell)` with screens PLAY, SHAPE, SPACE, LIBRARY on `F2`..`F5`, the
  layout drawn in AURORA "UI" at 100x30 and a compact variant at 80x24; footer tips per screen.
- `spec.py`: `AURORA_SPEC = InstrumentSpec(...)` (default skin `borealis`, default preset
  `glacier-choir`, `max_voices=8`).
- `__main__.py`: `main(argv=None) -> int: return run(AURORA_SPEC, argv)`.
- `data/skins/borealis.toml`, `solar-wind.toml`, `polar-night.toml`, `mono.toml` per the
  colourway table, each with an instrument-specific `[art] logo` (multi-line ASCII "AURORA"
  wordmark with sky motif), `density`, `idle` and `aurora` ramps; all load with zero warnings.

## Tests (names are binding; `trio/aurora/tests/`)

- `test_painter.py`: real SGR drag across bars sets heights along the path without gaps;
  right-drag erases; keyboard twin matches mouse results; even/odd/random commands.
- `test_waterfall.py`: driven by synthetic telemetry, glyph density is monotonic in magnitude;
  silent when no voices; deterministic in snapshot mode.
- `test_app_headless.py`: start `aurora` headlessly with the fake engine; `F2`..`F5` switch
  screens; a piano click produces `NoteOn`/`NoteOff`; skin cycling works; `Ctrl+Q` exits 0.
- `test_skins.py`: four skins load with zero warnings; required roles present; logo art fits
  100 columns.
- `test_snapshots.py`: golden PLAY and SHAPE at 100x30 and PLAY at 80x24 for every skin.
- `test_cli.py`: `aurora --selftest` returns 0; `aurora --render` writes a WAV.

## Acceptance criteria

- `aurora` launches in a real terminal (manually smoke-tested by you if you have one; otherwise
  state "not exercised" in the PR) and all headless tests pass.
- Matches the AURORA column of the difference contract; nothing copied from LOOM/DRIFT layouts.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

Sequencer/modulation (TRIO-015/016), packaging/launchers (TRIO-017).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-010-aurora-app`.
