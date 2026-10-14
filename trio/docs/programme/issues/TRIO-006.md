# [TRIO-006] Kit: skins, colourways and ASCII-art assets

Work in your local clone of `techrote/tuisynth` on **TRIO-006** and complete it end-to-end with the
local workflow in `trio/AGENTS.md`: implementation, tests, local CI, fixes, review record and
local squash-merge into `main` once every `trio/tools/ci.py` lane is green.

## Depends on

- TRIO-001 (#2) must be `done` in `trio/docs/programme/STATUS.md`. (Can run in parallel with TRIO-002..005.)

## Read first

1. `trio/AGENTS.md`
2. This issue file (`trio/docs/programme/issues/TRIO-006.md`) and its row in `STATUS.md`
3. `trio/docs/rag/05-SKINS-CONTRACT.md` (whole file)
4. `trio/docs/rag/04-TUI-UX-CONTRACT.md` section "Philosophy"
5. Reference only: `cpusynth/themes/*.toml`, `cpusynth/padsynth/themes.py`,
   `padsynth/themes/*.theme`

## Objective

A skin system that loads instrument art and colourways from data, can never crash the app,
and gives every widget a semantic style.

## Files (under `trio/kit/src/trio_kit/skins/`)

- `model.py`: frozen dataclasses `Style(fg, bg, bold, italic, underline, reverse)` with
  `to_pt() -> str` (prompt_toolkit style string such as `"fg:#cfe9e4 bg:#03121a bold"`), and
  `Skin(id, name, instrument, fps, palette, styles, glyphs, ramps, art, fallbacks)` with
  `style(role) -> str`, `glyphs(name, ascii=False) -> tuple[str, ...] | str`,
  `ramp(name, t: float) -> str` (hex colour, linear RGB interpolation between ramp stops),
  `art(name) -> list[str]`.
- `loader.py`: `REQUIRED_ROLES` (exact list from TRIO-SKINS), `load_skin(source: Path | str |
  bytes, *, instrument: str) -> tuple[Skin, list[str]]` implementing every validation rule in
  TRIO-SKINS "Validation"; never raises for content problems (only for programming errors such
  as a wrong argument type).
- `builtin.py`: the `mono` skin as an embedded TOML string (black/white/grey; ASCII glyphs;
  simple ASCII `logo` art "TRIO") and `MONO = load_skin(...)`.
- `library.py`: `SkinLibrary(instrument, factory_package, user_dir)` with `list() ->
  list[SkinInfo]` (factory, then user; `mono` always present), `load(id) -> tuple[Skin,
  list[str]]` (unknown id -> `mono` + warning), `next_id(current, step=+1)`.
- `color.py`: `force_mono()` decision from `NO_COLOR` env / flag; helpers for `#rrggbb`
  parsing and validation.
- `trio/kit/src/trio_kit/skins/data/kit-demo.toml`: a complete example skin exercising every
  section (used by tests and as documentation for instrument skin authors).

## Tests (names are binding; `trio/kit/tests/skins/`)

- `test_load_valid.py`: `kit-demo` loads with zero warnings; every required role resolves;
  ramps interpolate exactly at stops; art lines preserved; legacy `md-editor-theme/1.0`
  normalised; `cpusynth/themes/cyber-weather.toml` (read from the repo as text) loads with
  only "missing role" warnings and no exception.
- `test_hostile.py`: a parametrised corpus of at least 15 cases generated in the test
  (empty file, binary bytes, 200 KiB file, deep nesting, every section of the wrong type,
  invalid colours, unknown schema, ANSI escape in art, control chars in glyphs,
  double-width glyphs, 60-line art, ramp with 1 and 20 stops, non-string glyphs,
  `id` with spaces, a palette value that is a name instead of a colour) -> each returns a usable `Skin` (falls back to `mono` where
  the file is unusable) plus at least one warning, and never raises.
- `test_library.py`: listing order; unknown id fallback; `next_id` wraps both ways; a user
  skin with the same id as a factory skin is listed once, as `user`, and is the one loaded.
- `test_mono.py`: `NO_COLOR=1` forces `mono`; `mono` uses only ASCII glyphs.

## Acceptance criteria

- No skin content can raise from `load_skin`.
- Every rule in TRIO-SKINS "Validation" has at least one hostile test.
- `python trio/tools/ci.py` green on every lane.

## Out of scope

Rendering (TRIO-007), instrument skins (TRIO-010/012/014).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-006-skins`.
