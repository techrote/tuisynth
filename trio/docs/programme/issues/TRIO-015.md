# [TRIO-015] Stretch: step sequencer and arpeggiator

Work in `techrote/tuisynth` on **TRIO-015** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-010 (#11), TRIO-012 (#13) and TRIO-014 (#15) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/09-SEQUENCER-MODULATION-SPEC.md` section "Sequencer and arpeggiator"
4. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Events" (frame offsets) and "Engine"
5. `trio/docs/rag/00-CHARTER.md` section "Difference contract"
6. The three merged instrument `ui.py` files

## Objective

Sample-accurate step sequencing and arpeggiation in the kit, integrated into each instrument
in that instrument's own visual language, without changing any existing behaviour.

## Files

- `trio/kit/src/trio_kit/seq/`: `pattern.py` (`Step`, `Pattern`, validation, preset
  `extras.sequencer` round-trip), `transport.py` (`Transport` tempo/swing/state),
  `scheduler.py` (`Sequencer` hooked into `Engine` as a block-start callback that pushes
  `NoteOn`/`NoteOff` with `frame` offsets and guaranteed matching note-offs), `arp.py`
  (`Arpeggiator` modes/octaves/rates/latch, seeded random).
- `trio/kit/src/trio_kit/engine/engine.py`: add `Engine.add_block_hook(fn)` (called at the
  start of each block with `(block_start_frame, frames, sample_rate)`) - backwards compatible,
  with tests.
- `trio/kit/src/trio_kit/app/seqwidgets.py`: generic `StepGrid` widget logic (selection,
  toggling, velocity drag, probability right-click, keyboard twin) that instruments skin and
  place differently.
- Instrument integration (one `seq_ui.py` per instrument): AURORA spectral pillars on SPACE,
  LOOM knots on a thread in the panel row, DRIFT 16-cell pressure ring in a drawer; `Shift+F3`
  opens/focuses it; `Space` toggles transport; arp toggle and settings beside the grid.
- Update each instrument's preset validator to accept `extras.sequencer`.

## Tests (names are binding)

- `trio/kit/tests/seq/test_timing.py`: step frames within 1 frame of ideal at 120 BPM over 64
  steps at 44.1 and 48 kHz; swing offsets; tempo change mid-pattern keeps note pairing.
- `trio/kit/tests/seq/test_pairing.py`: every `NoteOn` has a matching `NoteOff` across stop,
  pattern edit, tempo change and panic.
- `trio/kit/tests/seq/test_arp.py`: ordering per mode (seeded random), octave ranges, rates,
  latch.
- `trio/kit/tests/seq/test_pattern_presets.py`: validation and preset round-trip.
- Per instrument `tests/test_seq_ui.py`: SGR click toggles a step; drag sets velocity;
  `Space` starts/stops; golden snapshot of the sequencer area for the default skin.

## Acceptance criteria

- All earlier tests remain green unchanged.
- Sequencer is visually distinct per instrument (difference contract).
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

MIDI clock follow unless fully tested with the fake MIDI backend; modulation (TRIO-016).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-015-sequencer`.
