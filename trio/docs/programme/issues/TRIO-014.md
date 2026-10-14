# [TRIO-014] DRIFT app: weather map and grain particles

Work in `techrote/tuisynth` on **TRIO-014** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-008 (#9) and TRIO-013 (#14) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/08-DRIFT-SPEC.md` sections "Field (performance) parameters", "UI" and the UI
   items under "Tests"
4. `trio/docs/rag/00-CHARTER.md` (DRIFT column and difference contract)
5. `trio/docs/rag/04-TUI-UX-CONTRACT.md` sections "Philosophy", "Mouse model", "App shell"
6. `trio/docs/rag/05-SKINS-CONTRACT.md` sections "Format", "Required roles",
   "Per-instrument factory colourways"
7. `trio/kit/src/trio_kit/demo.py` as the integration example. Do **not** reuse AURORA's tabs
   or LOOM's docked panel row.

## Objective

A playable DRIFT: a full-screen weather map where the storm cursor steers vowel and density,
real grains drawn as particles over drifting isobars, pop-over HUD drawers, a compact piano
strip, four skins and the shared CLI.

## Files (under `trio/drift/src/trio_drift/`)

- `widgets.py`: `WeatherMap` (isobars from a seeded drifting 2-D value-noise field with the
  skin `isobar` ramp; particles from telemetry `grains` with the skin `grain` ramp; storm
  cursor glyph; vowel labels A E I O U across the top, `storm`/`calm` axis labels; mouse capture
  drag -> `ParamSet("field.x"/"field.y")` along the path; hold -> `InstrumentEvent("gust",
  (True,))` / release `(False,)`; right-click recentre; wheel -> `gr.density`; keyboard twin per
  DRIFT "UI"; frozen in snapshot mode) and `Drawer` (overlay panel container, one open at a time,
  `Esc` closes).
- `ui.py`: `make_layout(shell)` - full-screen map, `F3` GRAIN drawer, `F4` AIR drawer (source,
  formant, wind), `F5` library overlay, `F2` focuses the map; compact piano strip and meters
  always visible; header shows the live grain count; compact 80x24 layout shrinks the map.
- `spec.py`: `DRIFT_SPEC` (default skin `squall`, preset `squall-choir`, `max_voices=6`,
  `legato_glide=True`).
- `__main__.py`: `main(argv=None) -> int: return run(DRIFT_SPEC, argv)`.
- `data/skins/squall.toml`, `desert-haze.toml`, `monsoon.toml`, `mono.toml` with an
  instrument-specific `[art] logo` (wind-swept "DRIFT"), `isobar`, `grain`, `cursor` glyphs and
  ramps per the colourway table; zero load warnings.

## Tests (names are binding; `trio/drift/tests/`)

- `test_weather_map.py`: real SGR drag emits `field.x/field.y` matching the path (0..1,
  y inverted so top = storm); hold without movement emits gust on, release emits gust off;
  right-click recentres; wheel changes density; keyboard twin equivalents.
- `test_particles.py`: number of drawn particles equals telemetry grains (capped by free
  cells); glyph by amplitude; isobars deterministic for a seed in snapshot mode.
- `test_drawers.py`: `F3`/`F4` open the right drawer, opening one closes the other, `Esc`
  closes; widgets inside drawers adjust params.
- `test_app_headless.py`, `test_skins.py`, `test_snapshots.py` (map at 100x30 and 80x24 with and
  without a drawer, every skin), `test_cli.py` (`drift --selftest`, `drift --render`) as in
  TRIO-010.

## Acceptance criteria

- Full-screen map + drawers model; steering by SGR drag works in headless tests.
- Matches the DRIFT column of the difference contract.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

Sequencer/modulation, packaging.

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-014-drift-app`.
