# TRIO implementation programme

## Objective

Deliver three radically different terminal pad / air / string synthesizers - **AURORA**
(spectral PADsynth pads), **LOOM** (waveguide strings) and **DRIFT** (granular air) - on a
shared, tested foundation (`trio_kit`), through dependency-ordered GitHub issues that an
autonomous coding agent (including OpenCode free-tier models) can complete end-to-end:
implementation, tests, PR, CI fixes and merge after automated checks.

Every issue body is an **execution prompt**. Its text is mirrored in
[`issues/`](issues) so agents can read it offline; the GitHub issue (with its comments) is the
authority if they differ.

## Initial plan (v0)

- Three issues, one per synth, each building a complete standalone Python app (engine, UI,
  presets, skins, MIDI) in its own folder, following the recovered synths' look and feel.
- One stretch issue adding a sequencer and modulation to all three.
- Each agent free to choose its DSP and layout, "as long as they sound like pads/air/strings".

## Review round 1 (against REVIEW.md and the recovered sources)

| # | Finding | Improvement |
|---|---|---|
| R1 | Three self-contained apps repeat the same infrastructure; the recovered CPU and Nice Glitch synths duplicated **eight identical defects** (MOD-001..008) for exactly this reason. | Build `trio_kit` once (params, engine, DSP, input, skins, TUI, shell) with contract tests; instruments contain only identity. |
| R2 | "Free to choose" guarantees convergence: the recovered synths all became similar subtractive pads with a chord-pad grid. | A written **difference contract** (synthesis domain, gesture, visualizer, layout, keyboard placement, skins) enforced in review ([charter](../rag/00-CHARTER.md)). |
| R3 | Identical package names prevented installation side by side and broke wheels. | Unique distributions/imports, `src/` layout, explicit package data, clean-venv install tests. |
| R4 | Whole-synth issues are far too large for free-tier models and impossible to review. | 17 issues, each a vertical slice of roughly 500-1,500 lines with its own tests. |
| R5 | Physical-model strings and granular clouds are per-sample recursive; naive Python would not run in real time. | Specify vectorisable algorithms: delay-chunked waveguide recursion, `lfilter` with carried state, per-grain NumPy overlap-add, FDN reverb with lines longer than a block. |
| R6 | Unsynchronised UI-to-DSP parameter writes and pitch-addressed note-offs caused stuck notes. | Event queue only; `ParamSnapshot` per block; `note_id` identity. |
| R7 | Mouse acceptance failed headlessly (PAD-001) and was never tested with real SGR input. | Headless driver that injects real SGR sequences; golden screen snapshots; manual Windows Terminal checklist. |
| R8 | Limiter/"never crash" claims were asserted, not tested. | Ceiling and non-finite guard tested on hot input and every preset; skin loader hostile-input corpus. |
| R9 | CI could not exercise audio/MIDI hardware and no one said so. | Device-free CI with explicit skips; `docs/ACCEPTANCE.md` for humans; nothing claims hardware results. |
| R10 | Model provenance was lost. | Mandatory `PROVENANCE.md` row per PR with the tool-reported model id. |
| R11 | Agents could merge red builds or modify preserved originals. | `trio/AGENTS.md` merge contract: every check green, fix budget, stop conditions, preserved paths forbidden. |
| R12 | Terminals send no key-up events, so keyboard notes either stick or cut short. | Timed gates with auto-repeat extension, a latch mode, and true note-off from the on-screen keyboard and MIDI. |

## Review round 2 (against the improved plan)

| # | Finding | Improvement |
|---|---|---|
| R13 | Shared envelopes/filters/delay/reverb had no owning issue, so each engine would re-invent them (and MOD-004's reversed delay could recur). | Added **TRIO-004 kit DSP library** before the engines. |
| R14 | The first code PR would merge with only the preservation CI, which does not test `trio/`. | TRIO-001 creates the path-filtered `trio.yml` workflow and `tools/check.py` before any feature code. |
| R15 | Three engine issues run in parallel and could each "improve" the kit, conflicting. | Instrument issues may only add small backwards-compatible kit extensions with tests; never change existing kit behaviour. |
| R16 | Snapshots of animated visualizers would be flaky. | Snapshot mode freezes clocks, seeds and telemetry ([TRIO-TEST](../rag/10-TESTING-CI-RELEASE.md)). |
| R17 | Performance gates on hosted runners are noisy. | Only a generous 20 s gate for 4 s of audio; real-time headroom is a manual acceptance item. |
| R18 | Stretch goals could destabilise the core before it ships. | Stretch issues depend on all three UIs being merged and must keep every earlier test green; release does not depend on them. |
| R19 | Free-tier agents lose context with long documents. | Each issue lists exactly which RAG sections to read; prompts are mirrored as files; AGENTS.md has a short free-tier section. |

## Improved target architecture

```text
                         trio_kit (one tested foundation)
   params+presets ── engine/voices/master ── dsp library ── input (keys, MIDI)
          │                   │                    │               │
          └──────── skins ── tui canvas+widgets ── app shell + on-screen keyboard
                                   │
          ┌────────────────────────┼─────────────────────────┐
          v                        v                         v
   AURORA (spectral)        LOOM (waveguide)          DRIFT (granular)
   paint harmonics          strum / bow strings       steer the storm
   aurora waterfall         vibrating strings         grain particle map
          └────────────── stretch: sequencer, modulation + post FX ──────────────┘
                                   │
                     packaging, launchers, acceptance, release
```

## Issue dependency graph

```text
TRIO-001 foundation + CI
  ├── TRIO-002 params/presets ──┐
  │        └── TRIO-003 engine ─┼── TRIO-005 input ──────────────┐
  ├── TRIO-004 dsp library ─────┤                                 │
  └── TRIO-006 skins ── TRIO-007 tui (needs 002) ── TRIO-008 shell + keyboard (needs 003, 005)
                                │                                 │
          TRIO-009 AURORA engine (003, 004) ── TRIO-010 AURORA UI (008, 009)
          TRIO-011 LOOM engine   (003, 004) ── TRIO-012 LOOM UI   (008, 011)
          TRIO-013 DRIFT engine  (003, 004) ── TRIO-014 DRIFT UI  (008, 013)
                                                                  │
          TRIO-015 sequencer + arpeggiator (010, 012, 014)        │
          TRIO-016 modulation + post-processing (015)             │
          TRIO-017 packaging, launchers, acceptance, release (010, 012, 014)
```

## Issue catalogue

| Code | GitHub | Title | Depends on | Primary outcome |
|---|---|---|---|---|
| TRIO-001 | [#2](https://github.com/techrote/tuisynth/issues/2) | Workspace foundation, packaging skeleton and TRIO CI | none | Four installable package skeletons, `tools/check.py`, `trio.yml` CI |
| TRIO-002 | [#3](https://github.com/techrote/tuisynth/issues/3) | Kit: parameter registry, validation and presets | 001 | Validated params, morph, atomic schema-versioned presets |
| TRIO-003 | [#4](https://github.com/techrote/tuisynth/issues/4) | Kit: events, voices, engine, master bus and audio backends | 002 | Exact block engine, `note_id` voices, limiter, device-free backends |
| TRIO-004 | [#5](https://github.com/techrote/tuisynth/issues/5) | Kit: DSP building blocks | 001 | Envelopes, filters, LFOs, delay, chorus, FDN reverb, limiter core |
| TRIO-005 | [#6](https://github.com/techrote/tuisynth/issues/6) | Kit: computer keyboard piano and USB MIDI input | 003 | Timed-gate keyboard, MIDI parser/ports/CC learn with fakes |
| TRIO-006 | [#7](https://github.com/techrote/tuisynth/issues/7) | Kit: skins, colourways and ASCII-art assets | 001 | Hardened skin loader, roles, art, ramps, live switching model |
| TRIO-007 | [#8](https://github.com/techrote/tuisynth/issues/8) | Kit: TUI canvas, mouse, widgets and headless driver | 002, 006 | Canvas, hit map, capture/drag, widgets, SGR test driver |
| TRIO-008 | [#9](https://github.com/techrote/tuisynth/issues/9) | Kit: on-screen keyboard, app shell and shared CLI | 003, 005, 007 | Clickable piano, shell overlays, shared flags, selftest/render |
| TRIO-009 | [#10](https://github.com/techrote/tuisynth/issues/10) | AURORA engine: spectral PADsynth | 003, 004 | Tables, voices, regeneration, presets |
| TRIO-010 | [#11](https://github.com/techrote/tuisynth/issues/11) | AURORA app: harmonic painter and aurora waterfall | 008, 009 | Playable AURORA with 4 skins |
| TRIO-011 | [#12](https://github.com/techrote/tuisynth/issues/12) | LOOM engine: waveguide strings, sympathetic bank, bodies | 003, 004 | Tuned strings, pluck/bow, sympathetic, body, presets |
| TRIO-012 | [#13](https://github.com/techrote/tuisynth/issues/13) | LOOM app: strum surface and vibrating strings | 008, 011 | Playable LOOM with 4 skins |
| TRIO-013 | [#14](https://github.com/techrote/tuisynth/issues/14) | DRIFT engine: granular air and formant clouds | 003, 004 | Sources, grain pool, formants, wind, presets |
| TRIO-014 | [#15](https://github.com/techrote/tuisynth/issues/15) | DRIFT app: weather map and grain particles | 008, 013 | Playable DRIFT with 4 skins |
| TRIO-015 | [#16](https://github.com/techrote/tuisynth/issues/16) | Stretch: step sequencer and arpeggiator | 010, 012, 014 | Sample-accurate sequencing in all three |
| TRIO-016 | [#17](https://github.com/techrote/tuisynth/issues/17) | Stretch: modulation oscillators, matrix and post-processing | 015 | Mod matrix and FX rack in all three |
| TRIO-017 | [#18](https://github.com/techrote/tuisynth/issues/18) | Packaging, launchers, documentation, acceptance and release | 010, 012, 014 | Wheels, launchers, user docs, `trio-v0.1.0` |

## Parallelism

After TRIO-001: TRIO-002, TRIO-004 and TRIO-006 can run in parallel. After TRIO-003 and
TRIO-004: the three engines (009, 011, 013) can run in parallel. After TRIO-008 and each
engine: its UI. TRIO-015 -> TRIO-016 are serial and touch all three instruments.
TRIO-017 can start once the three UIs are merged; it must include whichever stretch issues
are already merged.

## Definition of done (every issue)

- Dependencies closed; live `main` reconciled; issue comments read.
- All in-scope behaviour implemented exactly as specified by the issue and its RAG sections.
- Tests for every acceptance criterion; `python trio/tools/check.py --package all` green
  locally; no preserved file changed.
- RAG documents updated in the same PR if a contract changed.
- `PROVENANCE.md` row added.
- PR opened per `trio/AGENTS.md`, CI monitored and fixed within the fix budget, squash-merged
  only with every check green, post-merge `main` verified.
- No claim of audio-device, MIDI-hardware or real-terminal acceptance from CI.

## v0.1 release gate (TRIO-017)

- All of TRIO-001..014 merged; TRIO-015/016 merged or explicitly deferred in the release notes.
- `trio.yml` green on Linux and Windows for the release commit, including `--packaging`.
- Each instrument: `--selftest` passes from an installed wheel in a clean venv; all factory
  presets and skins load; golden snapshots pass; every difference-contract row demonstrably
  distinct (screenshots in docs from `--snapshot`-style text renders).
- `docs/ACCEPTANCE.md` exists with the manual checklist; results are recorded only when a
  human performs them.
- `PROVENANCE.md` complete for every merged PR.
