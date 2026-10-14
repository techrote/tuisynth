# Repository authority and maintenance

Read the selected synth's `docs/rag/INDEX.md`, review and import manifest before changing it.
The three folders deliberately remain independent despite identical `padsynth` module/distribution names.
Never import the sibling packages into the same interpreter. Use `tools/validate.py` for isolated tests.

This initial import is a preservation baseline: original files are SHA-256 checked. Do not modify them
as incidental cleanup, normalize their line endings, combine the synths, or drop features to make tests pass.
A later explicitly authorized repair must preserve recoverability, update the preservation policy openly,
add adversarial tests, remove only the corresponding strict xfails, and document audible changes.
Do not reinterpret xfails as success. Do not remove Nice Glitch's adaptation without explicit direction.

Do not commit virtual environments, dependency binaries, credentials, runtime locks, caches or bytecode.
Use device-free OfflineEngine/null paths in ordinary CI. Real audio/MIDI/Windows Terminal acceptance is
separate; do not claim it from headless tests. Retain source-linked Markdown with per-synth retrieval IDs.

## New TRIO programme

New synthesizer work lives in `trio/` and is governed by [`trio/AGENTS.md`](trio/AGENTS.md)
and the `[TRIO-0NN]` GitHub issues. TRIO work must not modify `cpusynth/`, `padsynth/`,
`niceglitchsynth/`, `evidence/`, `tools/validate.py`, `requirements-review.txt`, `REVIEW.md`
or `.github/workflows/ci.yml`; it may read them as reference material.
