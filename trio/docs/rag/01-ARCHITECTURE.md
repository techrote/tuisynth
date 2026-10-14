---
corpus: tuisynth
programme: trio
document_id: TRIO-ARCH
status: authority
---
# TRIO architecture and repository layout

## Layout

```text
trio/
  AGENTS.md                      execution contract for every TRIO issue
  README.md                      user-facing overview
  requirements-dev.txt           exact pins for CI and development
  tools/check.py                 single local/CI entry point (tests + packaging)
  docs/
    PROVENANCE.md                model/tool attribution per merged issue
    ACCEPTANCE.md                human-run audio/MIDI/terminal checklist (TRIO-017)
    programme/                   implementation programme and mirrored issue prompts
    rag/                         contracts (this corpus)
  kit/                           distribution "trio-kit", import package trio_kit
    pyproject.toml
    src/trio_kit/
      params.py presets.py       registry, validation, presets (TRIO-002)
      engine/                    events, voices, engine, backends, master bus (TRIO-003)
      dsp/                       envelopes, filters, LFOs, delay, chorus, reverb (TRIO-004)
      input/                     midi.py keyboard.py (TRIO-005)
      skins/                     theme loader, roles, art, ramps (TRIO-006)
      tui/                       canvas, hit map, mouse, widgets, test driver (TRIO-007)
      app/                       piano widget, app shell, CLI helpers (TRIO-008)
      seq/ mod/                  stretch: sequencer (TRIO-015), modulation/FX (TRIO-016)
    tests/
  aurora/  loom/  drift/         one distribution per instrument, same internal layout:
    pyproject.toml
    src/trio_<name>/
      __init__.py __main__.py    CLI entry (shared flags, see TRIO-UX)
      engine.py                  Instrument + Voice implementation (DSP issue)
      ui.py                      layout, gestures, visualizer (UI issue)
      params.py                  this instrument's ParamSpec list
      data/presets/*.json        factory presets (package data)
      data/skins/*.toml          factory skins (package data)
    tests/
```

Distribution names are unique (`trio-kit`, `trio-aurora`, `trio-loom`, `trio-drift`) and import
packages are unique (`trio_kit`, `trio_aurora`, `trio_loom`, `trio_drift`), so all four can be
installed into **one** development virtual environment. Use the `src/` layout and explicit
package data so wheels contain presets and skins.

## Runtime threads and data flow

```text
 terminal (prompt_toolkit)        MIDI (rtmidi callback)      sequencer (stretch, in engine)
        |  key/mouse events               | parsed messages
        v                                 v
   App shell + widgets  ---- Event(note_on/off, cc, param, panic, frame offset) ---->  EventQueue
        ^                                                                              |
        | read-only telemetry (voice states, spectra, grains, meters, cpu)             v
        +-------------------------- Telemetry ring <-----  Engine.render(frames)  <- audio callback
                                                              |  fixed 256-frame blocks
                                                              |  ParamSnapshot swapped per block
                                                              v
                                    Instrument voices -> instrument bus -> MasterBus -> device
```

- The **audio thread** owns all DSP state. It never blocks on the UI, never allocates large
  arrays per block after `prepare()`, and never raises out of the callback.
- The **UI thread** only enqueues events and reads telemetry snapshots. It never mutates DSP
  objects directly. This replaces the recovered synths' unsynchronised parameter swap.
- **Parameter changes** are queued and applied at the start of the next 256-frame block as one
  immutable `ParamSnapshot`, so a block always sees one consistent parameter set.
- **Notes are identified by `note_id`**, never by pitch, so transpose changes, repeated pitches
  and glissando never strand voices.
- **Telemetry** (for visualizers and meters) is published by the engine as small immutable
  snapshots at most once per block; the UI samples the latest one at its frame rate (20-30 fps).

## Package dependency rule

`trio_kit` depends only on NumPy, SciPy, prompt_toolkit and wcwidth; `sounddevice` and
`python-rtmidi` are optional extras imported lazily. Instruments depend on `trio_kit` and must
not import each other. An instrument issue may add a small backwards-compatible kit extension
with its own tests when genuinely needed; it must not change existing kit behaviour.

## Configuration and user data

Factory presets/skins are read with `importlib.resources` from package data. User presets,
user skins, MIDI CC-learn maps and session state live in a per-instrument user data directory:
`%APPDATA%\trio\<name>` on Windows, `$XDG_CONFIG_HOME/trio/<name>` or `~/.config/trio/<name>`
elsewhere, overridable with `--data-dir`. All writes are atomic (temp file + replace).
