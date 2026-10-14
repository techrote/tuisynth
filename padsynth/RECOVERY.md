# PadSynth: recovered source workspace

**Status:** preservation-reviewed, not production-qualified. The supplied runtime, factory assets,
launchers and existing tests are unchanged. Added files are documentation, manifests and review tests.

Start with the [RAG index](docs/rag/INDEX.md), [runbook](docs/rag/01-IDENTITY-RUNBOOK.md),
[architecture](docs/rag/02-ARCHITECTURE.md), [data/control contract](docs/rag/03-DATA-AND-CONTROLS.md)
and [review findings](docs/rag/04-TESTS-REVIEW.md).

Local review: **52 passed, 5 explicitly expected failures**. Expected failures represent
open defects/acceptance failures; they are not repaired or counted as passing functionality.
See the [test log](../evidence/local/padsynth.txt).

Archive: `padsynth.zip`; SHA-256 `419d4f504cbaa01eaeb46e3c58050466a6cca9cc015a365ba1a10bef8f139b67`.
[Import manifest](docs/IMPORT-MANIFEST.json) identifies all 19 preserved project files.
The original Windows virtual environment and runtime caches were not imported.
