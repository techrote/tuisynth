# [TRIO-013] DRIFT engine: granular air and formant clouds

Work in your local clone of `techrote/tuisynth` on **TRIO-013** and complete it end-to-end with the
local workflow in `trio/AGENTS.md`: implementation, tests, local CI, fixes, review record and
local squash-merge into `main` once every `trio/tools/ci.py` lane is green.

## Depends on

- TRIO-003 (#4) and TRIO-004 (#5) must be `done` in `trio/docs/programme/STATUS.md`.

## Read first

1. `trio/AGENTS.md`
2. This issue file (`trio/docs/programme/issues/TRIO-013.md`) and its row in `STATUS.md`
3. `trio/docs/rag/08-DRIFT-SPEC.md` sections "Sound identity", "DSP", "Tests" (DSP items)
4. `trio/docs/rag/00-CHARTER.md` section "Difference contract"
5. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Voices", "Engine", "DSP building
   blocks", "Performance"
6. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` rows "Unproven limiter claims" and
   "`filter.envd` unused param"
7. Background (read, do not copy code): Curtis Roads, *Microsound* (granular synthesis
   concepts) and the Csound manual's formant table appendix for the vowel values used in the
   spec

## Objective

The DRIFT sound engine as a `trio_kit` `Instrument`: seeded sources, a bounded grain pool
with Poisson scheduling, five-band vowel formants with morphing, wind, field parameters and
eight presets. No terminal UI in this issue.

## Files (under `trio/drift/src/trio_drift/`)

- `params.py`: `REGISTRY` with every parameter in DRIFT "Parameters" including `field.x`,
  `field.y` (modulatable) and `field.amount`.
- `sources.py`: `SourceBank(sample_rate, seed)` generating noise/tone/breath buffers per
  DRIFT "Sources", regenerated only when `src.color` changes (debounced, on the audio thread
  at a block boundary - generation is fast enough; assert < 50 ms in a test).
- `windows.py`: `window(kind, n) -> ndarray` for `hann`, `tukey`, `expodec`, `rexpodec`
  (exact zero endpoints; 2 ms fade-in for `expodec`).
- `grains.py`: `Grain` (slots dataclass) and `GrainPool(max_grains)` with `spawn(...)`,
  `render(block, out, source_mix)` implementing the bounded per-grain NumPy overlap-add,
  `active`, `dropped`.
- `formant.py`: `VOWELS` table exactly as in the spec, `vowel_params(vowel, shift, q) ->
  list[(freq, bw, gain_db)]`, `FormantBank(sample_rate)` (5 parallel `Biquad` band-pass per
  channel, 20 ms vowel smoothing, mix).
- `wind.py`: `Wind(sample_rate, seed)` gust signal and howl band-pass.
- `engine.py`: `DriftStream(Voice)` (pitch, velocity, ADSR, Poisson spawning from its own
  seeded `Generator`) and `DriftInstrument` (shared `GrainPool`, `FormantBank`, `Wind`,
  field/gust handling via params and `on_event("gust", (on,))`, shared reverb/delay);
  `telemetry()` returns `{"grains": [(pan, log2_ratio, amplitude, age01) ...], "density":
  current_density, "vowel": current_vowel}` (at most 96 entries).
- `data/presets/*.json`: the eight presets named in DRIFT "Factory presets".

## Tests (names are binding; `trio/drift/tests/`)

- `test_windows.py`: zero endpoints; `expodec` peak after ~2 ms; window sums are positive.
- `test_spawn.py`: `test_poisson_spawn_rate` (10 s at 50/s -> 500 +- 10 %, seeded);
  `test_pool_never_exceeds_max` and drop counting.
- `test_grains.py`: a single grain renders at the requested position, length, ratio and pan;
  block-boundary-straddling grains equal a single-block render of the same grain.
- `test_formant.py`: vowel A peaks within 15 % of 800/1,150 Hz; vowel I within 15 % of
  270/2,140 Hz; morph 0.5 between A and E lies between them; shift scales frequencies.
- `test_field.py`: `field.x = 0/1` with `field.amount = 1` selects A/U; `field.y` scales
  density 0.25x..4x; gust doubles density with 300 ms ramps.
- `test_params.py`: registry matches spec; every param used (method as in TRIO-009).
- `test_presets.py` and `test_performance.py` (6 streams, 96-grain pool, densest preset)
  as in TRIO-009.

## Acceptance criteria

- DRIFT "DSP" fully implemented; grain loop bounded by `gr.max`; no per-sample loops.
- No waveguide/spectral code here.
- `python trio/tools/ci.py` green on every lane.

## Out of scope

UI and skins (TRIO-014).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-013-drift-engine`.
