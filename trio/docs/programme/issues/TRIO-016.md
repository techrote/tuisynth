# [TRIO-016] Stretch: modulation oscillators, matrix and post-processing

Work in your local clone of `techrote/tuisynth` on **TRIO-016** and complete it end-to-end with the
local workflow in `trio/AGENTS.md`: implementation, tests, local CI, fixes, review record and
local squash-merge into `main` once every `trio/tools/ci.py` lane is green.

## Depends on

- TRIO-015 (#16) must be `done` in `trio/docs/programme/STATUS.md`.

## Read first

1. `trio/AGENTS.md`
2. This issue file (`trio/docs/programme/issues/TRIO-016.md`) and its row in `STATUS.md`
3. `trio/docs/rag/09-SEQUENCER-MODULATION-SPEC.md` section "Modulation oscillators, matrix
   and post-processing"
4. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Parameters" (`modulatable`),
   "Engine", "DSP building blocks"
5. `trio/docs/rag/00-CHARTER.md` section "Difference contract"
6. The three merged instrument `ui.py` files and `seq_ui.py` files

## Objective

LFO/envelope modulation sources, an 8-slot matrix applied at control rate, and a reorderable
post-processing rack with its own modulation oscillators, integrated into all three
instruments without changing their default sound (all slots empty and rack bypassed by
default).

## Files

- `trio/kit/src/trio_kit/mod/`: `sources.py` (`ModSources`: LFO1-3 with tempo sync via the
  sequencer `Transport`, `ModEnv`, velocity, modwheel, keytrack, note-random, pitchbend; global
  and per-voice evaluation), `matrix.py` (`ModMatrix` 8 slots, preset `extras.modulation`
  round-trip, application to a copy of `ParamSnapshot` per block with clamping), `rack.py`
  (`PostRack` with `Tremolo`, `RingMod`, `Phaser`, `Tape` units + existing chorus/delay/reverb,
  order list, bypass/mix per unit, each rack LFO exposed as a source).
- Engine integration: per-block hook applying global modulation; voices receive per-voice
  modulated snapshots (add a minimal backwards-compatible kit hook with tests).
- `trio/kit/src/trio_kit/app/modwidgets.py`: `ModMatrixGrid` (click a cell to route, drag
  vertically for amount, right-click clear, keyboard twin) and `Pedalboard` (ASCII boxes,
  drag to reorder, click to bypass, keyboard twin `Ctrl+Left/Right` to move).
- Per instrument `mod_ui.py` opened/focused with `Shift+F4`, drawn in that instrument's style.
- Each instrument's preset validator accepts `extras.modulation` and `extras.rack`.

## Tests (names are binding)

- `trio/kit/tests/mod/test_sources.py`: LFO shapes and rates at known phases; tempo sync at
  120 BPM; per-voice note-random constant within a note.
- `trio/kit/tests/mod/test_matrix.py`: routing, bipolar amounts, clamping, per-voice vs global,
  empty matrix leaves the snapshot identical.
- `trio/kit/tests/mod/test_rack.py`: tremolo/autopan constant power; ring-mod sum/difference
  partials; phaser notch movement; tape delay modulation depth; 20 s extreme-settings
  stability; continuity under random chunking; rack bypassed by default is bit-identical to no
  rack.
- `trio/kit/tests/mod/test_mod_presets.py`: matrix and rack order round-trip.
- Per instrument `tests/test_mod_ui.py`: SGR routing/reordering; golden snapshot of the MOD area;
  `test_default_sound_unchanged` (a factory preset renders bit-identically to before this issue -
  store a short checksum fixture generated from local `main` before your changes).

## Acceptance criteria

- Default sound of every factory preset unchanged; all earlier tests green.
- Visual identity per instrument preserved.
- `python trio/tools/ci.py` green on every lane.

## Out of scope

New synthesis engines, audio input, plugin formats.

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-016-modulation`.
