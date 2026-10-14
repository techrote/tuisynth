---
corpus: tuisynth
programme: trio
document_id: TRIO-LESSONS
status: authority
---
# Lessons from the recovered synths, converted into TRIO contracts

The repository's [REVIEW.md](../../../REVIEW.md) and the per-synth findings
([CPU](../../../cpusynth/docs/rag/04-TESTS-REVIEW.md),
[PadSynth](../../../padsynth/docs/rag/04-TESTS-REVIEW.md),
[Nice Glitch](../../../niceglitchsynth/docs/rag/04-TESTS-REVIEW.md)) describe three earlier
OpenCode free-tier builds. Each defect becomes a contract with a named test owner.
Read the original finding before implementing its TRIO counterpart.

| Recovered finding | What went wrong | TRIO contract | Owner issue |
|---|---|---|---|
| Identical `padsynth` package names | Three projects could not share an environment or a wheel | Unique distribution and import names; one dev venv holds all four | TRIO-001 |
| MOD-001 discrete morph | Discrete unison interpolated to 2.25 | Discrete/choice params switch at morph 0.5, tested at 0/0.25/0.49/0.5/0.75/1 | TRIO-002 |
| MOD-006 NaN accepted | Non-finite patch values reached DSP | `validate_value` rejects bool/str/None/NaN/Inf with a named error; clamping is reported | TRIO-002 |
| PAD-002 structural crashes | Wrong JSON types raised TypeError/AttributeError | Presets and skins return diagnostics for any structure; hostile-input tests | TRIO-002, TRIO-006 |
| MOD-002 note-off after transpose | Note-off addressed the new pitch | `note_id` identity for every note; transpose affects only new notes | TRIO-003 |
| MOD-008 same-pitch voices | Second note-off hit the releasing first voice | Voice ownership by `note_id`; repeated same-pitch overlap tests | TRIO-003 |
| MOD-003 render chunking | Non-block-multiple renders dropped tails | Remainder buffering; random-chunking equivalence property test | TRIO-003 |
| MOD-005 oversized callback | Callback tail left unwritten | `render(frames)` fills any size; never returns uninitialised memory | TRIO-003 |
| MOD-004 delay reversed | Delay read reversed history | Shared delay line with impulse/ramp/feedback tests in `trio_kit.dsp` | TRIO-004 |
| Unproven limiter claims | "Survives any load"/"limiter" asserted but untested | Ceiling 0.966 and non-finite guard asserted on hot input and every preset | TRIO-003 + each engine |
| Unsynchronised parameter swap | UI wrote DSP dicts while the callback read them | UI only enqueues; one `ParamSnapshot` per block | TRIO-003 |
| Stream start failure / lifecycle races | Cleanup unqualified | Backend failure falls back to `NullBackend`; `Ctrl+Q` shutdown order tested headlessly | TRIO-003, TRIO-008 |
| MOD-007 demo MIDI > 127 | Demo produced invalid note numbers | Event constructors reject out-of-range pitch/velocity; sequencer tests every event | TRIO-003, TRIO-015 |
| PAD-001 mouse mapping | SGR clicks all reported C4 | Real SGR injection tests for every key region, including black keys and depth velocity | TRIO-007, TRIO-008 |
| Theme hardening gaps | Hostile nested theme data not covered | Skin loader never raises; hostile-file test corpus | TRIO-006 |
| `filter.envd` unused param | Registered control with no audible path | Every registered param must be read by DSP or UI; registry coverage test per instrument | TRIO-009, TRIO-011, TRIO-013 |
| MOD-PKG-001 / PAD-PKG-001 | Wheels omitted data / discovery failed | `src/` layout, explicit package data, clean-venv install + `--selftest` in CI | TRIO-001, TRIO-017 |
| Unattributed model provenance | Builds could not be attributed | `PROVENANCE.md` row per issue branch with the tool-reported model id | every issue |
| Original suite red on arrival | One pre-existing test failed | Every issue merges only with every local `ci.py` lane green; Windows lane at milestones | every issue |

## Things the recovered synths did well (keep them)

- Mouse-first canvas with a hit map and a keyboard twin for every action.
- Semantic-role skins in `md-editor-theme/1.1`, with a restrained monochrome fallback.
- Device-free `OfflineEngine` testing and deterministic seeded renders.
- Three-row computer-keyboard velocity idea (TRIO keeps velocity keys instead, plus a
  chromatic layout) and velocity-by-click-depth on the on-screen keys.
- Rich footer tips explaining both mouse and keyboard actions per screen.
