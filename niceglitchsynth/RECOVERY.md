# Nice Glitch Synth: recovered source workspace

**Status:** preservation-reviewed, not production-qualified. The supplied runtime, factory assets,
launchers and existing tests are unchanged. Added files are documentation, manifests and review tests.

Start with the [RAG index](docs/rag/INDEX.md), [runbook](docs/rag/01-IDENTITY-RUNBOOK.md),
[architecture](docs/rag/02-ARCHITECTURE.md), [data/control contract](docs/rag/03-DATA-AND-CONTROLS.md)
and [review findings](docs/rag/04-TESTS-REVIEW.md).

Local review: **65 passed, 8 explicitly expected failures**. Expected failures represent
open defects/acceptance failures; they are not repaired or counted as passing functionality.
See the [test log](../evidence/local/niceglitchsynth.txt).

Archive: `niceglitchsynth.zip`; SHA-256 `ae570a12568ff0158682d3e844de143007fb877306dcc69ea0752eebdb8272f4`.
[Import manifest](docs/IMPORT-MANIFEST.json) identifies all 26 preserved project files.
The original Windows virtual environment and runtime caches were not imported.
