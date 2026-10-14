---
synth_id: cpusynth
document_id: CPU-DATA
---
# CPU Synth: data, controls and persistence

## A/B patch contract

`Patch` contains `name`, `char`, `morph`, dictionaries `a` and `b`, and ordered macro mappings.
`default_patch()` fills missing parameters; `morph_live()` blends A/B; `apply_macros()` adds scaled offsets
and clamps to registry bounds. Macros bind in mapping iteration order, which is part of the current behaviour.
There is no versioned schema or robust structural/numeric validation at load. Only load trusted presets
until MOD-006 and related structural checks are addressed. Discrete morphing has MOD-001 below midpoint.

`save_preset()` writes JSON directly; it is not an atomic, crash-safe replacement. Presets and themes
are resolved relative to the source package's parent directory. This is why data-less wheels are not
an accepted distribution route. Factory presets are `gale-ambience`, `hollow-pad`, `upper-air`, `veil-string`.
Factory themes are `cyber-weather`, `permutation-weather`, `restrained-monochrome`, `second-order-weather`.

## UI and theme contract

Screens: PLAY, PATCH, MIX, LIBRARY. `1`-`4` select screens; Tab/Shift+Tab moves focus; arrows adjust;
Space toggles the demo; `-`/`=` shifts octave; Ctrl+Q exits. Keyboard rows and mouse key-strip trigger timed
notes, and library operations select/save presets and preview/commit themes. Some demo notes exceed the
normal MIDI range because of MOD-007. Inspect the inherited [README](../../README.md) and
[ui.py](../../padsynth/ui.py) for the exact original mappings, not the standalone sibling's controls.

Themes are TOML, accepting `md-editor-theme/1.1` and legacy 1.0. `build_theme()` creates semantic role styles,
ramps, glyphs, art and patterns. Unknown fields can warn, but malformed nested objects are not comprehensively
hardened; imported factory themes compile in tests. Accepted layers/animations are not fully composed.
Use trusted theme files. The inherited README's blanket "never a crash" claim is not established.

## Parameter registry

This table is extracted from [param.py](../../padsynth/param.py); keys are retrieval anchors, not a guarantee
that every advertised control has an audible path. In particular `filter.envd` is registered but has no
corresponding engine read in this baseline, and pan LFO target handling needs further qualification.

| Key | Minimum | Maximum | Default | Discrete |
|---|---:|---:|---:|---|
| `osc.wave` | 0.0 | 1.0 | 0.55 | no |
| `osc.unison` | 1.0 | 6.0 | 2.0 | yes |
| `osc.detune` | 0.0 | 40.0 | 8.0 | no |
| `osc.semis` | -24.0 | 24.0 | 0.0 | yes |
| `osc.fine` | -99.0 | 99.0 | 0.0 | yes |
| `osc.sub` | 0.0 | 1.0 | 0.0 | no |
| `osc.noise` | 0.0 | 1.0 | 0.0 | no |
| `filter.mode` | 0.0 | 2.0 | 0.0 | yes |
| `filter.cut` | 40.0 | 16000.0 | 2400.0 | no |
| `filter.res` | 0.0 | 1.0 | 0.15 | no |
| `filter.envd` | 0.0 | 1.0 | 0.35 | no |
| `filter.key` | 0.0 | 1.0 | 0.4 | no |
| `amp.a` | 0.001 | 9.0 | 1.2 | no |
| `amp.d` | 0.01 | 9.0 | 1.0 | no |
| `amp.s` | 0.0 | 1.0 | 0.85 | no |
| `amp.r` | 0.02 | 12.0 | 3.0 | no |
| `amp.vel` | 0.0 | 1.0 | 0.5 | no |
| `flt.a` | 0.001 | 9.0 | 1.5 | no |
| `flt.d` | 0.01 | 9.0 | 1.4 | no |
| `flt.s` | 0.0 | 1.0 | 0.5 | no |
| `flt.r` | 0.02 | 12.0 | 3.5 | no |
| `flt.amt` | -1.0 | 1.0 | 0.4 | no |
| `l1.rate` | 0.02 | 8.0 | 0.25 | no |
| `l1.wave` | 0.0 | 3.0 | 0.0 | yes |
| `l1.tgt` | 0.0 | 3.0 | 0.0 | yes |
| `l1.dep` | 0.0 | 1.0 | 0.15 | no |
| `l2.rate` | 0.02 | 8.0 | 0.4 | no |
| `l2.wave` | 0.0 | 3.0 | 1.0 | yes |
| `l2.tgt` | 0.0 | 3.0 | 1.0 | yes |
| `l2.dep` | 0.0 | 1.0 | 0.1 | no |
| `pan.base` | -1.0 | 1.0 | 0.0 | no |
| `pan.spread` | 0.0 | 1.0 | 0.5 | no |
| `fx.chorus.mix` | 0.0 | 1.0 | 0.0 | no |
| `fx.chorus.rate` | 0.1 | 6.0 | 1.0 | no |
| `fx.chorus.depth` | 0.0 | 0.02 | 0.004 | no |
| `fx.delay.time` | 0.06 | 2.0 | 0.45 | no |
| `fx.delay.fb` | 0.0 | 0.9 | 0.25 | no |
| `fx.delay.mix` | 0.0 | 1.0 | 0.0 | no |
| `fx.reverb.size` | 0.2 | 1.6 | 1.0 | no |
| `fx.reverb.damp` | 0.0 | 0.9 | 0.35 | no |
| `fx.reverb.mix` | 0.0 | 1.0 | 0.35 | no |
| `master.level` | 0.0 | 1.0 | 0.8 | no |
| `master.drive` | 0.0 | 1.0 | 0.15 | no |
