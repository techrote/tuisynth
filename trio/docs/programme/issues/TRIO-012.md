# [TRIO-012] LOOM app: strum surface and vibrating strings

Work in `techrote/tuisynth` on **TRIO-012** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-008 (#9) and TRIO-011 (#12) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/07-LOOM-SPEC.md` sections "Strum surface model", "UI" and the UI items under
   "Tests"
4. `trio/docs/rag/00-CHARTER.md` (LOOM column and difference contract)
5. `trio/docs/rag/04-TUI-UX-CONTRACT.md` sections "Philosophy", "Mouse model", "App shell"
6. `trio/docs/rag/05-SKINS-CONTRACT.md` sections "Format", "Required roles",
   "Per-instrument factory colourways"
7. `trio/kit/src/trio_kit/demo.py` as the integration example (and the AURORA app in
   `trio/aurora/src/trio_aurora/ui.py` only if it is already merged) - do **not** copy AURORA's
   tabbed screen model

## Objective

A playable LOOM: one instrument surface with docked panels, animated strings you strum and
bow with the mouse, a sympathetic column, a short piano that also sets the strum chord, four
skins and the shared CLI.

## Files (under `trio/loom/src/trio_loom/`)

- `widgets.py`: `StringSurface` (draws `strum.strings` strings from telemetry with the skin
  `string` glyph ramp and bow marker; mouse capture strum: every row crossed between
  successive move events emits `InstrumentEvent("pluck_string" | "bow_string", ...)` with
  `crossing_velocity`; right-click mutes; keyboard twin `Up/Down`, `Enter`, `,`, `.`) and
  `SympatheticColumn` (12 resonator rows animated from telemetry, tuning label).
- `ui.py`: `make_layout(shell)` - single surface per LOOM "UI": strings + sympathetic column,
  the five docked panels (EXCITE, STRING, BODY, SYMPATHY, PLAY), short piano with a chord label;
  `F2` focuses strings, `F3` the panel row, `F4` the sympathetic column, `F5` library overlay;
  `/` toggles `play.mode`; compact 80x24 layout hides the sympathetic column behind `F4`.
- `spec.py`: `LOOM_SPEC` (default skin `rosewood`, preset `rosewood-harp`, `legato_glide` from
  bow mode).
- `__main__.py`: `main(argv=None) -> int: return run(LOOM_SPEC, argv)`.
- `data/skins/rosewood.toml`, `brass.toml`, `indigo-loom.toml`, `mono.toml` with an
  instrument-specific `[art] logo` (woven/thread motif "LOOM"), `string` glyph ramp, and
  colours per the colourway table; zero load warnings.

## Tests (names are binding; `trio/loom/tests/`)

- `test_strum_surface.py`: real SGR drag across string rows 3..9 emits one pluck per string in
  order with velocity increasing for a faster drag (inject timestamps through the driver's
  clock); bow mode emits `bow_string` on/off; right-click mute; keyboard twin equivalents.
- `test_chord_mode.py`: with `play.mode = chord`, piano clicks change the strum tuning shown
  on string labels and produce no direct notes; in `direct` they sound notes.
- `test_animation.py`: string glyph displacement grows with telemetry level; frozen in
  snapshot mode.
- `test_app_headless.py`, `test_skins.py`, `test_snapshots.py` (surface at 100x30 and 80x24 for
  every skin), `test_cli.py` (`loom --selftest`, `loom --render`) as in TRIO-010.

## Acceptance criteria

- Single-surface model (no tabs); strumming works by SGR drag in headless tests.
- Matches the LOOM column of the difference contract.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

Sequencer/modulation, packaging.

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-012-loom-app`.
