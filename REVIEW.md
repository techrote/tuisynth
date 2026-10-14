# Three-synth recovery review

## Scope and disposition

The user supplied `cpusynth.zip`, `padsynth.zip`, and `niceglitchsynth.zip` and requested testing, review,
separate GitHub folders, and RAG Markdown documentation. This import preserves all 71 project files,
not the machine-specific third-party environments. Original files were not repaired, reformatted or renamed.
No independently verifiable per-model build provenance was in those retained files.

## Executed local checks

| Check | Result |
|---|---|
| Safe archive enumeration and extraction | No absolute/traversal or symlink payloads accepted; original hashes recorded |
| Original-file SHA-256 verification | 71/71 byte-identical, including original tests and WAV |
| CPU Synth review | 63 passed; eight open-defect xfails |
| PadSynth review | 52 passed; five xfails (one original mouse acceptance, four malformed graph cases) |
| Nice Glitch review | 65 passed; eight open-defect xfails; adaptation tested separately |
| Unmodified PadSynth test suite | 45 passed / one failed on prompt-toolkit 3.0.52 and 3.0.53 |
| Original medley regeneration | SHA-256 exactly matches supplied 8.4-second stereo 44.1 kHz PCM16 WAV |
| CPU/Nice Glitch wheel creation | Builds succeed but omit required factory data; not install-qualified |
| Standalone PadSynth wheel creation | Fails flat-layout package discovery; source-directory launch remains available |

All pass counts above are **local**, not a substitute for actual GitHub Actions results.
The local native package versions differ from the Windows virtual environments in the supplied archives;
see `evidence/local/environment.json`. Both SciPy and CPU Synth's fallback filters were tested against
reference transfer functions. No native Windows `.pyd` files were executed or republished.

## Read the findings

[CPU Synth findings](cpusynth/docs/rag/04-TESTS-REVIEW.md),
[PadSynth findings](padsynth/docs/rag/04-TESTS-REVIEW.md), and
[Nice Glitch findings](niceglitchsynth/docs/rag/04-TESTS-REVIEW.md) distinguish confirmed reproductions,
known acceptance gaps, packaging defects, intentionally retained behaviour, and further static concerns.
There are eight shared modular defect IDs, two PadSynth defect IDs and two packaging defect categories.
The 21 xfail instances are not 21 independently distinct root causes.

The new `padsynth/tests/conftest.py` labels one exact pre-existing failure as strict xfail. It does not
edit the supplied test, suppress other exceptions or turn failures into assertions of success. Removing
that marker reproduces the original red suite. Strict xfails in added probes encode desired future contracts.

## Not established

No live device output, MIDI hardware, driver or latency qualification; no physical Windows Terminal mouse
acceptance; no subjective listening approval; no blanket security audit, sound-equivalence claim, benchmark
ranking or independent second-reviewer approval. Original creative/DSP behaviour is intentionally retained.

## Publication method

The connector accepts text rather than mounted binary files. A temporary hash-checked compressed text
transport imports the exact source/docs/test bytes on a dedicated GitHub branch. The original deterministic
PadSynth renderer reconstructs the included WAV; its original SHA-256 must match before commit. The temporary
payload is removed. Ordinary hosted preservation CI runs on the published content, not on a reconstruction
claim alone. This method does not send source to a third-party file host and does not require exposing credentials.
