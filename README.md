# TUI synth collection

Three owner-supplied OpenCode-era synth workspaces, preserved separately and reviewed on **14 October 2026**.
All **71 original project files** are retained byte-for-byte, including presets, themes, Windows launchers,
PadSynth's original test suite and its reproducible `demo-medley.wav`. Machine-specific environments,
empty nested Git metadata, bytecode, caches and stale runtime state are intentionally excluded.

## Choose a synth

| Folder | Implementation | Documentation | Local review |
|---|---|---|---|
| [cpusynth](cpusynth) | 44.1 kHz / 256-frame / 16-voice streaming NumPy synth; optional SciPy filter path | [RAG index](cpusynth/docs/rag/INDEX.md) · [review](cpusynth/docs/rag/04-TESTS-REVIEW.md) | 63 passed, 8 known xfails |
| [padsynth](padsynth) | Standalone graph-based, deterministic whole-buffer audition/WAV synth | [RAG index](padsynth/docs/rag/INDEX.md) · [review](padsynth/docs/rag/04-TESTS-REVIEW.md) | 52 passed, 5 known xfails |
| [niceglitchsynth](niceglitchsynth) | Distinct streaming variant with adaptive effect shedding and deliberate block skipping | [RAG index](niceglitchsynth/docs/rag/INDEX.md) · [review](niceglitchsynth/docs/rag/04-TESTS-REVIEW.md) | 65 passed, 8 known xfails |

**180 passed / 21 strict expected failures locally.** Expected failures are documented open defects,
not passing functionality or repairs. This is a preservation-and-review baseline, **not production/audio-device
qualification**. The original PadSynth suite, run without the added marker, reports 45 passes and one failure.
All original runtime files remain unchanged; source fixes were not silently applied during recovery.

## Launch and isolation

All three projects identify themselves internally as `padsynth` 0.1.0. **Use separate virtual environments
and run from the chosen source folder.** Do not `pip install` the three into a shared environment.
The two modular projects use `Setup.cmd` / `Start.cmd`; standalone PadSynth uses `1Setup.cmd` / `0Start.cmd`.
The [per-synth runbooks](cpusynth/docs/rag/01-IDENTITY-RUNBOOK.md) explain the exact commands and the
unresolved wheel-packaging restrictions. These are source workspaces, not standalone `.exe` releases.

## Reproduce the review

```sh
python -m venv .review-venv
# Activate .review-venv using your shell's normal activation command.
python -m pip install -r requirements-review.txt
python tools/validate.py
```

The validator checks the preserved SHA-256 manifests and runs a new pytest process in each folder,
preventing package-name collisions. Known xfails are strict: unexpected passes require review; other
failures remain failures. CI uses hosted Linux and Windows without an audio/MIDI device. See the actual
[Actions results](https://github.com/techrote/tuisynth/actions) for hosted status; local evidence alone
must not be described as Windows acceptance.

[Local evidence](evidence/local) · [packaging report](evidence/packaging.json) ·
[collection review](REVIEW.md) · [maintenance rules](AGENTS.md)

## Provenance and limitations

Per-folder `docs/IMPORT-MANIFEST.json` files contain original archive identities and every retained file hash.
The owner identifies these as OpenCode free-tier builds. Exact individual model attribution is unverified.
The CPU/Nice Glitch inherited READMEs say MIT, but no standalone LICENSE text was supplied; no new
blanket license or authorship is invented for the collection. Source, documentation and evidence are
provided under the owner's publication request.

Live audio/MIDI hardware, sustained real-time performance, subjective sound quality and real Windows Terminal
mouse interaction remain unqualified. Nice Glitch's intentional adaptive/glitch behaviour is preserved.
