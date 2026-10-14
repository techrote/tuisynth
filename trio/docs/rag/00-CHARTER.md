---
corpus: tuisynth
programme: trio
document_id: TRIO-CHARTER
status: authority
---
# TRIO charter: three radically different TUI pad / air / string synthesizers

## Goal

Build three new, independently installable terminal synthesizers under `trio/`, sharing one
tested foundation package (`trio_kit`) but deliberately **different in synthesis domain, sound,
interaction metaphor, primary mouse gesture, visualizer and layout**. All three are focused on
pads, air and strings, are mouse-first with a keyboard twin for every action, render artistic
ASCII/Unicode interfaces, ship several skins/colourways, include an on-screen mouse-clickable
keyboard, and accept computer-keyboard and USB-MIDI note input.

Stretch goals: an integrated step sequencer/arpeggiator, and modulation oscillators with a
modulation matrix and post-processing effects.

The three preserved folders (`cpusynth/`, `padsynth/`, `niceglitchsynth/`) are **reference
material only**. They are never modified, imported or copied wholesale. Their recorded defects
are converted into explicit contracts in [11-LESSONS-FROM-RECOVERY.md](11-LESSONS-FROM-RECOVERY.md).

## The three instruments

| | **AURORA** | **LOOM** | **DRIFT** |
|---|---|---|---|
| Package / CLI | `trio_aurora` / `aurora` | `trio_loom` / `loom` | `trio_drift` / `drift` |
| Sound focus | Lush, slowly evolving **pads** and choirs of partials | Plucked, strummed and bowed **strings** with sympathetic resonance | **Air**: breath, wind, whistle, vowel-shaped noise clouds |
| Synthesis domain | Frequency domain: Nasca **PADsynth** spectral wavetables (additive profile -> IFFT) | Time domain: **digital waveguide** strings (extended Karplus-Strong) + modal body + sympathetic bank | Micro-time stochastic: **granular** clouds over noise/tone sources + **formant** filter bank |
| Excitation | None; continuous looped tables | Pluck impulse / continuous bow noise | Poisson-scheduled grains |
| Polyphony model | 8 table-playback voices | 8 plucked or 4 bowed strings + 12 sympathetic resonators | Paraphonic: up to 6 note streams sharing a 96-grain pool |
| Signature mouse gesture | **Paint** the harmonic spectrum by dragging across 64 bars | **Strum** by dragging across animated string lines; **bow** by holding and dragging | **Steer** a storm cursor across an XY weather map; hold to gust |
| Visualizer | Aurora **waterfall** of the live spectrum | **Vibrating strings** whose displacement follows the voices | **Particle cloud** of real active grains over isobar contours |
| Screen model | Tabbed screens (PLAY, SHAPE, SPACE, LIBRARY) | One instrument surface with docked panels | Full-screen field with pop-over HUD drawers |
| On-screen keyboard | Full-width 3-octave piano along the bottom | Short piano that also selects the strum chord | Compact 2-octave strip in the lower-right HUD |
| Factory skins | `borealis`, `solar-wind`, `polar-night`, `mono` | `rosewood`, `brass`, `indigo-loom`, `mono` | `squall`, `desert-haze`, `monsoon`, `mono` |

### Difference contract (reviewers must enforce)

A change is rejected if it makes two instruments converge on any row above: for example
reusing AURORA's harmonic painter in DRIFT, giving LOOM a tabbed screen model, or adding a
4x4 chord-pad grid (the recovered synths' metaphor) to all three. Shared code lives in
`trio_kit`; *instrument identity* (DSP, layout, gestures, art, skins, presets) never does.

## Shared, non-negotiable product requirements

1. **Mouse first, keyboard everything.** Every mouse action has a documented keyboard twin.
2. **On-screen keyboard** that is mouse-clickable with true note-off on mouse release,
   velocity from click depth, drag glissando and exact cell-to-note hit mapping.
3. **Computer keyboard** chromatic two-row tracker layout plus octave/velocity keys.
4. **USB MIDI** input (note on/off/velocity, sustain, mod wheel, pitch bend, panic, CC learn),
   optional at runtime and never a crash when unavailable.
5. **Artistic ASCII art**: hand-designed frames, logos and live visualizers, driven by skin data.
6. **Skins/colourways**: at least four per instrument including the guaranteed-safe `mono`,
   switchable live, validated at load, never able to crash the app.
7. **Device-free operation**: `--no-audio`, `--selftest` and offline WAV rendering for CI.
8. **Safe output**: a master limiter guarantees peaks never exceed -0.3 dBFS and no NaN/Inf.

## Non-goals for v0.1

GUI windows, plugin formats (VST/CLAP), sample playback/import, network features, audio input,
a bundled Python runtime or `.exe` builder, multi-timbral MIDI, and microtonal tuning files.

## Licence and attribution

No licence is selected for this repository. Do not add one. Every implementation branch records
the actual model/tool that wrote it in [../PROVENANCE.md](../PROVENANCE.md); never guess.
