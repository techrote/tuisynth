---
synth_id: padsynth
document_id: PAD-DATA
---
# PadSynth: data, controls and persistence

## Formats and assets

Patch schema: `padsynth-patch/1.0`, JSON objects containing a stable id, node list, one output and
allowlisted node types/parameters. Inspect [factory patches](../../patches) and the `PARAM_SPECS`,
`NODE_TYPES`, `validate_patch()` and `topo_order()` definitions in [padsynth.py](../../padsynth.py).
This graph schema is **not interchangeable** with the A/B flat parameter dictionaries used by the two
modular siblings. Unknown types, missing outputs, graph cycles and numeric non-finites are covered;
malformed structural types still crash validation (PAD-002).

Factory patch identities: `weather-machine`, `needle-rain`, `ion-cell`, `cyan-fog`, `amber-strike`.
Theme files: `neon-circuitry.theme`, `teal-core.theme`, `aqua-pink.theme`, `purpleblue-engine.theme`.
Theme schema is an implemented subset of `md-editor-theme/1.1`, with legacy 1.0 normalization.
Config schema is `padsynth-config/1.0` in [padsynth.conf](../../padsynth.conf). The program does not rewrite
that manually maintained config. Session restore, locks and transient state use `.padsynth/` by default;
the uploaded stale lock/session were deliberately not imported.

## Interaction contract

Pads/voice/mod/browser/piano are separate tiles. `run_command()` owns command dispatch and the command
palette provides a recovery route. Important emergency routes are Ctrl+P (palette), Ctrl+T (restore),
Ctrl+Q (quit), F10 (ribbon), F1 (help). Ordinary tracker keys are separate from the modular siblings'
three-row piano mapping. Piano geometry maps upper black-key regions and lower full-velocity safe rows.
Pure geometry tests pass; the supplied headless SGR acceptance does not (PAD-001).

The original file lists many configurable capabilities. Do not infer that every accepted theme animation,
layout ratio, resource budget or accessibility option is fully composed/enforced at runtime. The source
notes that ambient animation tracks are accepted but not composed as a timer-driven animation system.

## Preserved demo

[demo-medley.wav](../../demo-medley.wav) is **8.4 seconds, stereo PCM16, 44,100 Hz**.
Its SHA-256 is `61848a4723606b2675d82e9251d3db43fa0b6a4d7ba56e09ef7176cf09d2e7f2`.
Running the original source with `--demo` and its supplied config/factory assets reproduced it byte-for-byte
in the local review. This establishes a concrete source/asset relationship, not subjective audio quality.
[pianosweep.txt](../../pianosweep.txt) and [pianosweep2.txt](../../pianosweep2.txt) are preserved small
workspace notes/logs, not additional synth implementations.
