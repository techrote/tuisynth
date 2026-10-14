---
corpus: tuisynth
synth_id: niceglitchsynth
document_id: NG-INDEX
status: preserved-source-reviewed
review_date: 2026-10-14
---
# Nice Glitch Synth RAG index

## Retrieval scope and authority

This corpus describes **`niceglitchsynth/` only**. All three recovered projects call themselves
`padsynth` internally; do not merge their APIs, schemas, tests, installation environments or evidence.
Use `synth_id: niceglitchsynth` when retrieving. Aliases: Nice Glitch Synth, niceglitchsynth, uploaded `niceglitchsynth.zip`.
The owner identifies the batch as OpenCode free-tier work; individual model attribution is unverified.

Authority order: preserved source and factory files; reproducible tests and recorded evidence;
these review notes; original prose claims. A claim in an inherited README is not acceptance evidence.
Original bytes are anchored by [IMPORT-MANIFEST.json](../IMPORT-MANIFEST.json). There are no restored
Git commits from the empty nested Git metadata. Do not infer authors or commit history.

## Retrieval map

| Need | Document | Stable retrieval ID |
|---|---|---|
| Installation, entry point, isolation, provenance | [Identity and runbook](01-IDENTITY-RUNBOOK.md) | NG-RUN |
| Runtime ownership and signal/data flow | [Architecture and source map](02-ARCHITECTURE.md) | NG-ARCH |
| Presets, themes, controls and persistence | [Data and controls](03-DATA-AND-CONTROLS.md) | NG-DATA |
| Tests, open defects, exclusions and acceptance | [Tests and review](04-TESTS-REVIEW.md) | NG-REVIEW |

## Safe maintenance rules

Treat this as an archival baseline. Make sound-changing repairs on a separate reviewed branch;
do not silently overwrite the preserved files or loosen strict xfail assertions. A deliberate later
repair must move original files into a versioned archive or explicitly revise the preservation policy,
retain their original hashes, update the tests and explain any audible difference.
Do not copy the sibling implementation over this one because the package name matches.
