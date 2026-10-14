# [TRIO-005] Kit: computer keyboard piano and USB MIDI input

Work in `techrote/tuisynth` on **TRIO-005** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-003 (#4) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/03-INPUT-CONTRACT.md` sections "Computer keyboard" and "USB MIDI"
4. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` section "Events"
5. Reference only: `cpusynth/padsynth/midi.py`

## Objective

Pure, testable note input from the computer keyboard (timed gates, latch, octave, velocity) and
from USB MIDI (parser, port handling, reconnect, CC learn), producing kit engine events.

## Files (under `trio/kit/src/trio_kit/input/`)

- `keyboard.py`: `KEY_LAYOUT` (dict key -> semitone offset from C3 exactly per TRIO-INPUT),
  `KeyboardPiano(note_ids, gate_ms=450, octave=0, velocity=0.7)` with
  `press(key: str, now: float) -> list[Event]` (handles note keys, `-`, `=`, `[`, `]`, `'`;
  returns `[]` for unrelated keys), `tick(now) -> list[Event]` (expired gates -> `NoteOff`),
  `release_all() -> list[Event]`, properties `octave`, `velocity`, `latch`, `held_pitches`.
  Clamp octave to -3..+3 and final pitch to 0..127 (keys outside are ignored).
- `midi.py`: `parse_midi(message, channel_filter=0, bend_range=2.0) -> list[MidiMessage]`
  (small dataclasses: `MidiNoteOn`, `MidiNoteOff`, `MidiCC`, `MidiBend`, `MidiPanic`),
  `MidiNoteMap(note_ids)` converting parsed messages to engine events (`NoteOn`/`NoteOff` with
  `note_id`, `Sustain`, `ModWheel`, `PitchBend`, `Panic`, `ControlChange` for other CCs),
  `MidiBackend` protocol (`list_ports()`, `open(index)`, `close()`, `set_callback(fn)`),
  `RtMidiBackend` (lazy `import rtmidi`), `FakeMidiPort`, and `MidiInput(backend, sink,
  channel=0)` with `available`, `error`, `ports`, `open(index_or_name)`, `close()`,
  `poll_reconnect(now)` (2 s interval; reopens a previously named port when it reappears),
  `malformed_count`.
- `midimap.py`: `MidiMap(path)` storing `{cc_number: param_key}` in `midi-map.json`
  (`trio_kit.userdata.atomic_write_text`), `arm(param_key)`, `feed(cc, value) -> tuple[key,
  value01] | None` (when armed: bind and disarm), `lookup(cc)`, `clear(cc=None)`, `load()`,
  `save()`. Invalid files load as empty with a warning, never raise.

## Tests (names are binding; `trio/kit/tests/input/`)

- `test_keyboard.py`: `test_layout_matches_contract` (every key -> expected MIDI note at octave 0),
  `test_gate_expires_without_repeat`, `test_repeat_extends_gate`, `test_latch_toggles`,
  `test_octave_and_velocity_keys`, `test_out_of_range_notes_ignored`,
  `test_octave_change_does_not_strand_held_note` (note-off uses the original `note_id`).
- `test_midi_parse.py`: byte-sequence cases for every message type in TRIO-INPUT including
  velocity-0 note-on, 14-bit bend extremes and centre, channel filter, clock/active
  sensing/SysEx ignored, short/garbage messages counted as malformed.
- `test_midi_notemap.py`: repeated note-on without note-off releases the previous voice id;
  sustain mapping; CC 120/123 -> `Panic`.
- `test_midi_input.py`: `FakeMidiPort` delivery to sink; `RtMidiBackend` missing ->
  `available is False` with message; reconnect after the fake port disappears and returns.
- `test_midimap.py`: learn binds next CC; persistence round-trip; corrupt file -> empty map.

## Acceptance criteria

- No test opens a real MIDI port; CI does not install python-rtmidi.
- All TRIO-INPUT "Computer keyboard" and "USB MIDI" behaviour implemented and tested.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

On-screen keyboard widget and MIDI picker UI (TRIO-008).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-005-input`.
