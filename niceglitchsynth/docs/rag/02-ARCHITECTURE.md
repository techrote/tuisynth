---
synth_id: niceglitchsynth
document_id: NG-ARCH
---
# Nice Glitch Synth: architecture and source map

## Streaming architecture

`padsynth.__main__.main()` selects theme, constructs audio/offline engine, loads a Patch, optionally
opens MIDI, constructs DemoTransport and then PadSynthApp. UI/MIDI/demo producers enqueue note, sustain,
panic and transpose tuples. `_drain()` applies events before the next block.

`PolySynth` has **16 voice slots**, **six maximum unison oscillators**, **512-sample wavetable data**,
**44,100 Hz** sample rate and **256-frame** blocks. Voices own oscillator phase, amplitude/filter ADSRs,
LFO phases, filter state and pan. Random initial phase/pan uses the global NumPy RNG.

Signal flow: waveform-table blend/unison + optional sub/noise -> per-voice biquad -> amplitude envelope
and pan -> summed left/right -> chorus -> echo -> reverb -> tanh/master level -> DC blocker -> stereo output.
The DSP is a fixed chain, not the standalone sibling's JSON node graph.
`Patch.live()` supplies the parameter dictionary; `_push_live()` distributes it to DSP objects.
The dictionary swap across objects is not proven to be an atomic callback-wide transaction.

`OfflineEngine.render(n)` renders this chain into RAM. MOD-003 means non-block-multiple calls discard
unused tail samples; use multiples of 256 for now. Equal seeds reproduce a given implementation in the
same environment; there is no claim that CPU Synth and Nice Glitch are sample-identical.

`PadSynthApp` paints a custom cell canvas/hit map and uses a refresh thread. DemoTransport uses a timer
thread and heap scheduler. Keyboard gates are timed releases because terminals do not report ordinary
key-up. Cleanup is in `PadSynthApp.run()`'s `finally` path; all lifecycle races remain outside qualification.

## Distinctive adaptive/glitch policy

This variant removes CPU Synth's optional SciPy filter path, uses list-based biquad iteration,
precomputed block indexes and vectorized OnePole smoothing. It additionally tracks callback pressure.
These are observed source differences, not measured speedup claims.

| Degrade stage | Original callback policy |
|---|---|
| 0 | Full synthesis and all effects |
| 1 | Bypass reverb |
| 2 | Also bypass chorus and echo |
| 3 | Limit unison to two and disable auxiliary sub/noise |
| 4 | Additionally output silence on alternating callbacks |

Underflow raises the pressure counter by three; slow callbacks by one. Four accumulated pressure units
raise a stage; twelve easy callbacks lower it. Bypassed effects retain stale state. Returning them to
service can be discontinuous. OfflineEngine remains full quality and does not simulate adaptation.
`tests/test_degradation.py` verifies escalation, recovery and stage-four alternating silence.
Do not remove this policy or merge CPU Synth over it as an incidental cleanup.

## Source anchors

Paths and symbols below are generated from the preserved Python AST; line numbers refer to the imported bytes.

| Source | Top-level symbols and lines |
|---|---|
| [padsynth/__init__.py](../../padsynth/__init__.py) | Package exports/constants |
| [padsynth/__main__.py](../../padsynth/__main__.py) | `build_patch` (L12); `main` (L26) |
| [padsynth/demo.py](../../padsynth/demo.py) | `_Scheduler` (L40); `DemoTransport` (L61); `_interval_name` (L170) |
| [padsynth/engine/__init__.py](../../padsynth/engine/__init__.py) | Package exports/constants |
| [padsynth/engine/core.py](../../padsynth/engine/core.py) | `_drain` (L19); `AudioEngine` (L43); `OfflineEngine` (L173); `make_engine` (L242) |
| [padsynth/engine/fx.py](../../padsynth/engine/fx.py) | `DelayLine` (L16); `OnePole` (L40); `Chorus` (L75); `_vshift_delay` (L111); `Echo` (L120); `Reverb` (L145); `MasterBus` (L201) |
| [padsynth/engine/synth.py](../../padsynth/engine/synth.py) | `_make_wavetables` (L22); `ADSR` (L36); `Biquad` (L125); `Voice` (L166); `PolySynth` (L187); `_lfo_wave` (L379) |
| [padsynth/midi.py](../../padsynth/midi.py) | `MidiInput` (L14) |
| [padsynth/param.py](../../padsynth/param.py) | `ParamSpec` (L25); `spec` (L115); `default_patch` (L119); `lerp` (L123); `morph_live` (L127); `apply_macros` (L138); `group_of` (L153); `Patch` (L158); `load_preset` (L199); `save_preset` (L203); `list_presets` (L207) |
| [padsynth/themes.py](../../padsynth/themes.py) | `Skin` (L68); `_lerp_hex` (L159); `_is_hex` (L167); `load_theme` (L172); `build_theme` (L177); `list_themes` (L271); `load_any_theme` (L277) |
| [padsynth/ui.py](../../padsynth/ui.py) | `to01` (L61); `from01` (L67); `_Shim` (L74); `_Ctx` (L81); `_CanvasControl` (L151); `PadSynthApp` (L162) |
| [padsynth/util.py](../../padsynth/util.py) | `midi_to_name` (L7); `midi_to_freq` (L11); `clamp` (L15); `fmt_hz` (L19); `fmt_time` (L25); `fmt_pct` (L31); `fmt_cents` (L35); `fmt_int` (L39) |
