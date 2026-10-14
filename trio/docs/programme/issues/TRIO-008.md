# [TRIO-008] Kit: on-screen keyboard, app shell and shared CLI

Work in `techrote/tuisynth` on **TRIO-008** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-003 (#4), TRIO-005 (#6) and TRIO-007 (#8) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/03-INPUT-CONTRACT.md` section "On-screen keyboard widget"
4. `trio/docs/rag/04-TUI-UX-CONTRACT.md` sections "App shell", "Shared command-line flags",
   "Headless test driver"
5. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Engine", "Backends"
6. `trio/docs/rag/01-ARCHITECTURE.md` section "Configuration and user data"
7. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` rows PAD-001 and "Stream start failure"

## Objective

Everything an instrument needs around its own layout: a mouse-clickable piano with true
note-off, the shell (header, footer tips, help, palette, skin/MIDI/preset overlays, undo),
shared CLI flags including `--selftest`, `--render` and `--snapshot`, and a kit demo instrument
that proves the whole stack end-to-end.

## Files (under `trio/kit/src/trio_kit/app/`)

- `piano.py`: `PianoWidget(first_note, octaves, note_ids, sink, velocity_rows=True)` meeting
  TRIO-INPUT exactly (geometry, depth velocity, mouse-up note-off, drag glissando, optional
  legato via `legato_glide`, right-click latch, wheel octave, keyboard twin, highlights for
  notes sounding from any source via a `sounding: set[float]` input).
- `spec.py`: dataclass `InstrumentSpec(id, name, version, registry, make_instrument,
  make_layout, factory_package, default_skin, default_preset, max_voices, extras_validator,
  legato_glide=False)`; `make_layout(shell) -> Layout` returns the instrument's root widget,
  its screen/panel map for `F2`..`F5`, and footer tips.
- `shell.py`: `Shell(spec, engine, backend, midi, skins, presets, args)` building the
  `CanvasApp`: header/footer per TRIO-UX, F-key and Ctrl bindings from the App shell table,
  computer-keyboard routing through `KeyboardPiano` (with a `tick` timer), MIDI sink, CC learn,
  undo/redo (50 steps of `ParamSet` history), telemetry polling, orderly shutdown on `Ctrl+Q`
  (release notes -> stop backend -> close MIDI -> exit application).
- `overlays.py`: help, command palette (fuzzy filter over every shell command), skin picker
  with live preview/commit/revert, MIDI picker (ports, channel, bindings), preset library
  (load, save, save-as with `TextField`, rename, delete user preset). Saving stores current
  params plus `instrument.get_extras()`. Loading calls `Engine.apply_preset(params, extras)`
  (add it to the kit engine in this issue, with tests), which queues the parameter changes and
  calls `set_extras` on the audio thread at the next block boundary.
- `cli.py`: `build_parser(spec)` with every flag in TRIO-UX "Shared command-line flags";
  `run(spec, argv=None) -> int` dispatching to list commands, `--selftest`, `--render`,
  `--snapshot` or the interactive shell.
- `selftest.py`: `selftest(spec) -> int` per TRIO-UX (loads all factory presets and skins,
  renders 2 s of C4-E4-G4 per preset, checks finite + ceiling + non-silent, renders every
  screen headlessly at 100x30 and 80x24, prints a summary, never opens a device or terminal).
- `render.py`: `render_wav(spec, path, notes, seconds, preset, seed)` writing PCM16 stereo with
  the stdlib `wave` module.
- `trio/kit/src/trio_kit/demo.py`: a `SineInstrument`-based `DEMO_SPEC` with a two-screen
  layout using kit widgets and the piano, ending with
  `if __name__ == "__main__": raise SystemExit(run(DEMO_SPEC))` so it runs as
  `python -m trio_kit.demo [flags]`.

## Tests (names are binding; `trio/kit/tests/app/`)

- `test_piano_geometry.py`: for a 2-octave piano at a known position, every cell maps to the
  expected key (white and black), via real SGR clicks: `test_every_key_cell_sgr_click`;
  `test_click_depth_velocity` (top row 0.35, bottom row 1.0); `test_mouse_up_sends_note_off`;
  `test_drag_glissando_sequence`; `test_right_click_latch`; `test_wheel_shifts_octave`;
  `test_keyboard_twin_plays_cursor_key`.
- `test_shell_keys.py`: F1 help opens/closes; F6/Shift+F6 cycle skins; F9 sends `Panic`;
  Ctrl+P palette lists commands and executes one; Ctrl+Z/Ctrl+Y undo/redo a fader change;
  letter keys reach `KeyboardPiano` when no text field is focused and do not when one is.
- `test_shell_shutdown.py`: `Ctrl+Q` releases held notes, stops the (fake) backend, closes the
  (fake) MIDI port in that order and exits with code 0.
- `test_cli.py`: `--version`, `--list-skins`, `--list-presets`, `--list-midi` (fake backend),
  `--render` writes a valid WAV with expected length, `--snapshot 100x30` prints a frame,
  `--selftest` returns 0 for `DEMO_SPEC` and 1 when a factory preset is broken (fixture).
- `test_backend_fallback.py`: a failing audio backend falls back to `NullBackend` with a header
  status message, not a crash.
- `test_demo_snapshots.py`: golden snapshots of the demo instrument screens (100x30, 80x24,
  skins `kit-demo` and `mono`).

## Acceptance criteria

- The piano passes every SGR geometry test; mouse release always ends the note.
- `python -m trio_kit.demo --selftest` returns 0 in CI.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

Instrument DSP and layouts (TRIO-009..014), sequencer/modulation (TRIO-015/016).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-008-shell`.
