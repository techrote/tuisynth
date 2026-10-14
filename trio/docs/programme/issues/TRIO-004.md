# [TRIO-004] Kit: DSP building blocks

Work in `techrote/tuisynth` on **TRIO-004** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-001 (#2) must be closed. (Independent of TRIO-002/003; can run in parallel.)

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Fixed numbers", "DSP building blocks",
   "Performance"
4. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` row MOD-004
5. Reference only: `cpusynth/padsynth/engine/fx.py` (shows the reversed-delay bug MOD-004)

## Objective

Stateful, block-vectorised DSP units that all three instruments share, each proven by
continuity, response and stability tests.

## Files (under `trio/kit/src/trio_kit/dsp/`)

`__init__.py`, `adsr.py` (`Adsr`), `biquad.py` (`Biquad`, `biquad_coeffs(mode, freq, q,
sample_rate, gain_db=0)`), `lfo.py` (`Lfo`), `delay.py` (`DelayLine`), `chorus.py` (`Chorus`),
`stereo_delay.py` (`StereoDelay`), `reverb.py` (`Reverb`), `smoothing.py` (`Smoother`: one-pole
parameter smoothing over a time constant, vectorised per block via `lfilter`).

Common interface: constructor takes `sample_rate` and the unit's parameters; `process(x) ->
ndarray` for mono `(n,)` or stereo `(n, 2)` as documented per unit; `set_params(**kw)` (applied
from the next call); `reset()`. Units never allocate arrays proportional to total stream
length; per-block temporaries are fine.

Behaviour per unit is defined in the TRIO-ENGINE "DSP building blocks" table. Additional
binding details:

- `Adsr.render(n) -> ndarray(n)` returns envelope values 0..1 (times velocity scaling handled by
  the caller); stage changes may happen mid-block; `finished` true once release reaches
  `< 1e-5`.
- `Biquad` modes: `lp`, `bp`, `hp`, `peak`; parameters `freq`, `q`, `gain_db`; frequency clamped
  to `[20, 0.45 * sample_rate]`; `q` clamped to `[0.3, 20]`.
- `Lfo(shape, rate_hz, phase=0.0, seed=0).render(n)`.
- `DelayLine(max_seconds, sample_rate)`: `write(x)`, `read(delay_samples, n)` for fixed or per-sample
  delay arrays (linear interpolation), `process(x, delay_samples, feedback=0.0)` requiring
  `delay_samples >= n` when `feedback != 0` (raise `ValueError` otherwise).
- `Reverb(sample_rate, size, damp, mix)`: stereo in/out; 8 lines with base lengths
  1327, 1601, 1867, 2111, 2503, 2887, 3301, 3701 samples at 48 kHz, scaled by
  `sample_rate / 48000` and by `size`, then raised to at least `BLOCK + 32`. Target decay
  `RT60 = 0.5 + 3.0 * size` seconds; per-line feedback gain `10 ** (-3 * length /
  (sample_rate * RT60))`; one-pole damping per line with coefficient `damp`. Input is
  distributed to all lines; L/R outputs take alternating line sums.

## Tests (names are binding; `trio/kit/tests/dsp/`)

- `test_continuity.py`: for every unit, processing 9,600 samples of seeded noise in 30 random
  chunk sizes (1-256) equals processing in one call (tolerance 1e-6).
- `test_adsr.py`: stage timing within 1 block; 99 % rule for decay/release; retrigger during
  release is click-free (max step < 0.05).
- `test_biquad.py`: LP and HP magnitude at cutoff for Q 0.707 within -3 dB +-1 dB; BP peak
  within 5 % of centre; stability at Q 20 for 20 s of noise.
- `test_lfo.py`: shape values at phases 0, 0.25, 0.5, 0.75; rate accuracy; seeded S&H repeatable.
- `test_delay.py`: `test_delay_is_chronological` (write 0..7, read delay 4 -> 4,5,6,7; the MOD-004
  regression), impulse response position, fractional delay interpolation, feedback decays.
- `test_chorus_delay.py`: chorus delay range stays within 7-20 ms; ping-pong alternates channels;
  feedback 0.9 remains finite for 20 s.
- `test_reverb.py`: impulse tail decays below -90 dBFS within 15 s at size 1.6; output finite;
  `mix=0` returns input unchanged.
- `test_performance_dsp.py`: processing 10 s of stereo audio through chorus+delay+reverb
  completes in < 10 s wall time (prints realtime factor).

## Acceptance criteria

- All units implemented per contract and tests above green on both CI platforms.
- No per-sample Python loops in production code.

## Out of scope

Instrument-specific DSP (spectral tables, waveguides, grains), engine integration.

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-004-dsp`.
