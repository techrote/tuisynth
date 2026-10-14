---
corpus: tuisynth
programme: trio
document_id: TRIO-INDEX
status: authority
---
# TRIO RAG index

Retrieval scope: everything under `trio/`. These documents are the design authority for the
TRIO implementation programme. They do **not** describe `cpusynth/`, `padsynth/` or
`niceglitchsynth/`, which have their own corpora and must not be modified.

Authority order: current local `main` code and tests; the issue file being executed
(`trio/docs/programme/issues/TRIO-0NN.md`) and its `STATUS.md` notes;
[`trio/AGENTS.md`](../../AGENTS.md); these RAG documents;
[the programme](../programme/IMPLEMENTATION-PROGRAMME.md).

| Need | Document | Retrieval ID |
|---|---|---|
| Goals, the three instruments, difference contract | [00-CHARTER.md](00-CHARTER.md) | TRIO-CHARTER |
| Layout, threads, data flow, packaging rule | [01-ARCHITECTURE.md](01-ARCHITECTURE.md) | TRIO-ARCH |
| Params, presets, events, voices, engine, master bus | [02-AUDIO-ENGINE-CONTRACT.md](02-AUDIO-ENGINE-CONTRACT.md) | TRIO-ENGINE |
| Computer keyboard, on-screen keyboard, MIDI | [03-INPUT-CONTRACT.md](03-INPUT-CONTRACT.md) | TRIO-INPUT |
| Canvas, mouse, widgets, shell keys, CLI flags, headless driver | [04-TUI-UX-CONTRACT.md](04-TUI-UX-CONTRACT.md) | TRIO-UX |
| Skin format, validation, colourways, ASCII art | [05-SKINS-CONTRACT.md](05-SKINS-CONTRACT.md) | TRIO-SKINS |
| AURORA spectral pad instrument | [06-AURORA-SPEC.md](06-AURORA-SPEC.md) | TRIO-AURORA |
| LOOM waveguide string instrument | [07-LOOM-SPEC.md](07-LOOM-SPEC.md) | TRIO-LOOM |
| DRIFT granular air instrument | [08-DRIFT-SPEC.md](08-DRIFT-SPEC.md) | TRIO-DRIFT |
| Stretch: sequencer, modulation, post-processing | [09-SEQUENCER-MODULATION-SPEC.md](09-SEQUENCER-MODULATION-SPEC.md) | TRIO-SEQMOD |
| Test layers, CI, packaging, release, provenance | [10-TESTING-CI-RELEASE.md](10-TESTING-CI-RELEASE.md) | TRIO-TEST |
| Recovered-synth defects mapped to contracts | [11-LESSONS-FROM-RECOVERY.md](11-LESSONS-FROM-RECOVERY.md) | TRIO-LESSONS |
| Local VM workflow, LM Studio host, model roster, OpenCode config | [12-LOCAL-WORKFLOW-AND-MODELS.md](12-LOCAL-WORKFLOW-AND-MODELS.md) | TRIO-LOCAL |

If code and a RAG document disagree, the branch that changes the contract must update the
RAG document on the same branch and list it under "Contract changes" in its review record.
