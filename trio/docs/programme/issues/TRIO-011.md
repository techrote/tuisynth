# [TRIO-011] LOOM engine: waveguide strings, sympathetic bank and bodies

Work in `techrote/tuisynth` on **TRIO-011** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-003 (#4) and TRIO-004 (#5) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/07-LOOM-SPEC.md` sections "Sound identity", "DSP", "Tests" (DSP items)
4. `trio/docs/rag/00-CHARTER.md` section "Difference contract"
5. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Events" (`InstrumentEvent`),
   "Voices", "Engine", "DSP building blocks", "Performance"
6. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` rows "Unproven limiter claims" and
   "`filter.envd` unused param"
7. Background (read, do not copy code): Jaffe & Smith, "Extensions of the Karplus-Strong
   Plucked-String Algorithm" (Computer Music Journal, 1983) and Julius O. Smith's online book
   "Physical Audio Signal Processing", chapters on digital waveguides and Karplus-Strong
   (<https://ccrma.stanford.edu/~jos/pasp/>)

## Objective

The LOOM sound engine as a `trio_kit` `Instrument`: exact delay-chunked waveguide strings
with pluck and bow excitation, a stable sympathetic bank, modal bodies, the strum tuning
model and eight presets. No terminal UI in this issue.

## Files (under `trio/loom/src/trio_loom/`)

- `params.py`: `REGISTRY` with every parameter in LOOM "Parameters" (`exc.mode` changes the
  voice limit: 8 pluck / 4 bow); `validate_extras` for an optional custom sympathetic tuning
  list (`extras.sym_custom`: up to 12 MIDI note numbers).
- `waveguide.py`: `Waveguide(sample_rate, max_delay)` with `set_pitch(midi)`,
  `set_decay(t60)`, `set_brightness(b)`, `process(excitation) -> ndarray` implementing the
  delay-chunked recursion in LOOM "String model" exactly; `reference_process(...)` (slow,
  per-sample, test-only module `tests/reference.py` - not in the package).
- `excitation.py`: `PluckExciter` (burst, hardness LPF, pick-position comb, seeded) and
  `BowExciter` (band-passed seeded noise, attack 80 ms, rosin flutter, 150 ms release fade).
- `sympathetic.py`: `SympatheticBank(sample_rate)` with 12 `Waveguide`s, tuning modes
  `scale`/`drone`/`chord`, the quiet-only retune rule, input low-pass and mix; scales per spec.
- `body.py`: `BODY_MODES` table (type -> list of `(freq_hz, q, gain_db)`, 6-10 modes each,
  docstring noting they are artistic approximations) and `BodyResonator` (parallel `Biquad`
  band-pass bank, size scaling, mix).
- `strum.py`: `StrumModel(strings=8)` deriving per-string pitches from held notes or the
  default tuning per LOOM "Strum surface model"; `crossing_velocity(rows_per_second)`.
- `engine.py`: `LoomVoice` and `LoomInstrument`; `on_event` handles
  `("pluck_string", (index, velocity))`, `("bow_string", (index, velocity, on))`,
  `("mute_string", (index,))` and `("strum", (direction, velocity))` (applies `strum.spread`);
  the bus runs body -> sympathetic -> shared reverb; `telemetry()` returns
  `{"strings": [{"pitch", "level", "phase", "bowed"} ...], "sympathetic": [levels x 12],
  "chord": [pitches]}`.
- `data/presets/*.json`: the eight presets named in LOOM "Factory presets".

## Tests (names are binding; `trio/loom/tests/`)

- `test_waveguide.py`: `test_chunked_equals_reference` (1e-6), `test_tuning_within_5_cents`
  (MIDI 28, 40, 52, 64, 76, 88; FFT peak + parabolic interpolation),
  `test_t60_within_25_percent` (1, 4, 10 s), `test_pitch_retarget_click_free`.
- `test_excitation.py`: pluck burst length, pick-position comb notch, bow envelope timing,
  determinism with seed.
- `test_sympathetic.py`: in-tune excitation >= 6 dB more sympathetic energy than out-of-tune;
  no return path (main output unchanged when `sym.mix = 0`); chord mode retunes only quiet
  resonators.
- `test_body.py`: each body type's response has peaks near its mode frequencies; `size`
  scaling.
- `test_strum.py`: chord spreading across strings; default tuning; crossing velocity formula;
  `strum` event timing with `strum.spread`.
- `test_stability.py`: 20 s at maximum decay/brightness/coupling stays finite; limiter gain
  reduction <= 1 dB before the master limiter (measure pre-master peak).
- `test_params.py`: registry matches spec; every param used (same method as TRIO-009);
  voice limit follows `exc.mode`.
- `test_presets.py` and `test_performance.py`: as in TRIO-009 (8 pluck voices + full bank).

## Acceptance criteria

- LOOM "DSP" fully implemented; bowing documented and tested as a linear excitation
  approximation; no granular/spectral code here.
- No per-sample Python loops in production code.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

UI and skins (TRIO-012).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-011-loom-engine`.
