# [TRIO-009] AURORA engine: spectral PADsynth

Work in your local clone of `techrote/tuisynth` on **TRIO-009** and complete it end-to-end with the
local workflow in `trio/AGENTS.md`: implementation, tests, local CI, fixes, review record and
local squash-merge into `main` once every `trio/tools/ci.py` lane is green.

## Depends on

- TRIO-003 (#4) and TRIO-004 (#5) must be `done` in `trio/docs/programme/STATUS.md`.

## Read first

1. `trio/AGENTS.md`
2. This issue file (`trio/docs/programme/issues/TRIO-009.md`) and its row in `STATUS.md`
3. `trio/docs/rag/06-AURORA-SPEC.md` sections "Sound identity", "DSP", "Tests" (DSP items)
4. `trio/docs/rag/00-CHARTER.md` section "Difference contract"
5. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Voices", "Engine", "DSP building
   blocks", "Performance"
6. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` rows "Unproven limiter claims" and
   "`filter.envd` unused param"
7. Background on the algorithm (read, do not copy code): Paul Nasca's PADsynth description,
   <https://zynaddsubfx.sourceforge.io/doc/PADsynth/PADsynth.htm>

## Objective

The AURORA sound engine as a `trio_kit` `Instrument`, with background table regeneration,
eight factory presets and full offline tests. No terminal UI in this issue.

## Files (under `trio/aurora/src/trio_aurora/`)

- `params.py`: `REGISTRY = ParamRegistry([...])` with every parameter in AURORA "Parameters"
  (keys, ranges, defaults, kinds, curves exactly; mark `flt.cut`, `lfo.depth`, `amp.*`,
  `osc.width`, `spec.tilt` and FX mixes `modulatable=True`); `validate_extras(extras) ->
  tuple[dict, list[str]]` for `harmonics`.
- `tables.py`: `generate_tables(sample_rate, spectral_params, harmonics, zones=7, n=2**18) ->
  TableSet` (pure, vectorised, deterministic); `TableSet` holds `zone_f0`, `left`, `right`
  float32 arrays; `TableCache`.
- `regen.py`: `TableRegenerator` worker thread with 150 ms debounce, `request(params,
  harmonics)`, `latest() -> TableSet | None`, `close()` (joins the thread).
- `engine.py`: `AuroraVoice(Voice)` and `AuroraInstrument(Instrument)` implementing the voice
  and bus behaviour in AURORA "DSP" using `trio_kit.dsp` (`Adsr`, `Biquad` for the filter
  modes, `Lfo`, `Chorus`, `StereoDelay`, `Reverb`); 50 ms crossfade on table swap;
  `telemetry()` returns `{"spectrum": <64-band magnitude 0..1 float list of the current table
  set>, "levels": <per-voice envelope levels>}`; `make_instrument()` factory.
- `data/presets/*.json`: the eight factory presets named in AURORA "Factory presets", each with
  a distinct harmonic profile and parameter set that matches its name (document the intent in a
  `description` field inside `extras`).

## Tests (names are binding; `trio/aurora/tests/`)

- `test_params.py`: registry matches the spec table; `test_every_param_is_used` (registry
  coverage: each key is read by `engine.py` or `tables.py`, checked by instrumenting the
  `ParamSnapshot` access in a 1 s render with all keys set to non-defaults).
- `test_tables.py`: harmonic peak positions within 1 %; bandwidth increases with `spec.bw`;
  determinism; seed changes waveform not magnitude; skips harmonics above 0.45 x sample rate;
  generation of 7 zones x 64 harmonics in < 10 s.
- `test_voice.py`: pitch of a held note within 3 cents (FFT peak) for MIDI 36, 60, 84; stereo
  width correlation bounds from the spec; filter cutoff and envelope behave; release finishes
  the voice.
- `test_regen.py`: changing harmonics during playback: no step > 0.2 between consecutive
  samples, output finite, regenerator thread joined after `close()`.
- `test_presets.py`: every factory preset parses with zero warnings and renders 2 s of C4-E4-G4
  finite, non-silent (RMS > -40 dBFS), peak <= 0.966.
- `test_performance.py`: 4 s of the densest preset with 8 voices renders in < 20 s; print the
  realtime factor.

## Acceptance criteria

- AURORA "DSP" section fully implemented; difference contract respected (no waveguide or
  granular code here).
- No per-sample Python loops in voice rendering.
- `python trio/tools/ci.py` green on every lane.

## Out of scope

UI, skins, CLI wiring (TRIO-010).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-009-aurora-engine`.
