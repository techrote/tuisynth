# [TRIO-003] Kit: events, voices, engine, master bus and audio backends

Work in `techrote/tuisynth` on **TRIO-003** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-002 (#3) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Fixed numbers", "Events", "Voices",
   "Engine", "Master bus", "Backends", "Performance"
4. `trio/docs/rag/01-ARCHITECTURE.md` section "Runtime threads and data flow"
5. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` rows MOD-002, MOD-003, MOD-005, MOD-008,
   limiter, parameter swap, stream start, MOD-007
6. Reference only: `cpusynth/padsynth/engine/core.py` and `synth.py` (do not copy their bugs)

## Objective

The real-time core every instrument plugs into: exact block rendering for any callback size,
`note_id`-owned voices, per-block parameter snapshots, a provably safe master bus and
device-free/sounddevice backends.

## Files (under `trio/kit/src/trio_kit/engine/`)

- `__init__.py` re-exporting the public API below.
- `events.py`: frozen dataclasses `NoteOn`, `NoteOff`, `Sustain`, `PitchBend`, `ModWheel`,
  `ControlChange`, `ParamSet`, `InstrumentEvent`, `Panic` (fields per TRIO-ENGINE; constructors validate ranges and
  raise `ValueError`); `NoteIds` (thread-safe monotonic `next()`); `EventQueue(maxsize=4096)`
  with `push(event) -> bool` (non-blocking; on overflow drop the oldest `ParamSet`, never a
  `NoteOff`; return `False` if the event itself was dropped) and `drain() -> list`.
- `params.py` (engine side): `ParamSnapshot` (immutable mapping wrapper with attribute-free
  `__getitem__`, `get`, `items`) and `ParamState(registry)` that applies queued `ParamSet`s and
  yields a new snapshot per block.
- `voices.py`: `Voice` and `Instrument` abstract base classes (methods per TRIO-ENGINE "Voices",
  with default no-op `on_event`, `get_extras` returning `{}`, `set_extras`, `close`),
  `VoiceManager(max_voices)` implementing allocation, stealing with 5 ms fade, sustain,
  panic fade 10 ms, `note_id` mapping, `active_count`.
- `engine.py`: `Engine(instrument, sample_rate=48000, block=256, max_voices=8, seed=0)` with
  `push`, `render(frames) -> np.ndarray` (float32, shape `(frames, 2)`), `telemetry()`,
  `close()`; `OfflineEngine` subclass with `render_notes(notes, seconds, ...)` helper for tests.
  Block processing order exactly as TRIO-ENGINE "Engine". Events with `frame > 0` split the block.
- `master.py`: `MasterBus(sample_rate)` with DC blocker, drive, the vectorised limiter defined in
  TRIO-ENGINE "Master bus", hard clip, non-finite guard and counters.
- `telemetry.py`: `Telemetry` dataclass (voices, cpu_load, limiter_gain_db, nonfinite_resets,
  dropped_events, callback_errors, instrument: dict) published as an immutable snapshot.
- `backends.py`: `NullBackend`, `SoundDeviceBackend` (lazy import; callback per TRIO-ENGINE;
  start failure -> close, message, fall back), `open_backend(engine, device=None,
  no_audio=False) -> Backend` and `list_devices() -> list[str]` (empty list if sounddevice
  missing).
- `testing.py`: `SineInstrument` (sine voices with linear 5 ms attack/release; used by tests
  and later UI tests) and `FakeEngine` (records pushed events, returns silence, exposes canned
  telemetry).

## Tests (names are binding; `trio/kit/tests/engine/`)

- `test_events.py`: range validation, `NoteIds` uniqueness under 8 threads, queue overflow
  policy keeps note-offs, `InstrumentEvent` delivered to `Instrument.on_event` at the block
  start (and at its `frame` when given).
- `test_render_exactness.py`: `test_chunked_render_equals_whole` (Hypothesis is not allowed;
  use 50 seeded random chunkings of 4,800 frames incl. sizes 1, 255, 256, 257, 1024),
  `test_any_callback_size_fully_written` (sizes 1..2048 sampled; no NaN, no uninitialised
  garbage: fill output buffer with NaN first).
- `test_voices.py`: `test_transpose_does_not_strand_note` (MOD-002 analogue: note_on id1 at 60,
  producer transposes, note_off id1 releases the original voice),
  `test_same_pitch_overlap_each_note_off_releases_own_voice` (MOD-008), `test_steal_prefers_released`,
  `test_sustain_holds_and_releases`, `test_panic_releases_everything_with_fade`.
- `test_params_snapshot.py`: param changes apply only at block starts; one block sees one
  consistent snapshot.
- `test_master.py`: `test_ceiling_never_exceeded` (+24 dB hot noise and full-scale square),
  `test_nonfinite_block_is_silenced_and_counted`, `test_dc_removed`, `test_limiter_vectorised_matches_reference`
  (compare to a slow per-sample reference implementation in the test).
- `test_backends.py`: `test_null_backend_runs`, `test_sounddevice_missing_falls_back`
  (monkeypatch the import), `test_callback_exception_writes_silence` (call the callback
  function directly with a fake `outdata`).
- `test_determinism.py`: equal seed + events -> identical output; different seed -> different
  output for `SineInstrument` with random start phase.

## Acceptance criteria

- Every bullet in the listed TRIO-ENGINE sections implemented and tested.
- No per-sample Python loops in `engine.py` or `master.py` (the test-only references are fine).
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

Envelopes/filters/FX (TRIO-004), MIDI/keyboard (TRIO-005), any UI.

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-003-engine`.
