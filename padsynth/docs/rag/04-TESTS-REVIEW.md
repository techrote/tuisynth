---
synth_id: padsynth
document_id: PAD-REVIEW
review_date: 2026-10-14
status: open-defects-preserved
---
# PadSynth: tests and review

## Disposition

**Import/preservation accepted; production/audio-device acceptance not established.**
This is a single-reviewer source inspection plus executable characterization, not an independent external audit.
No supplied runtime, factory asset, launcher or pre-existing test was changed. All original project files
are checked against [IMPORT-MANIFEST.json](../IMPORT-MANIFEST.json).

Local final suite: **52 passed, 5 strict expected failures**. See
[test log](../../../evidence/local/padsynth.txt), [JUnit](../../../evidence/local/padsynth.xml),
[environment](../../../evidence/local/environment.json) and [packaging evidence](../../../evidence/packaging.json).
Expected failures are open deficiencies, not green functionality. Unexpected passes fail the gate so a
future fix must be reviewed and its expected-failure marker removed. Unrelated failures remain hard failures.

## Coverage and findings

The original suite was run unmodified with both prompt-toolkit 3.0.52 and the uploaded 3.0.53:
**45 passed, one failed** in each. The final review adds 11 probes and marks the exact pre-existing
mouse acceptance as strict xfail in [tests/conftest.py](../../tests/conftest.py), without editing the original
[test file](../../tests/test_padsynth.py). The review probes are in [test_review.py](../../tests/test_review.py).

| ID | Priority / evidence | Finding and repair acceptance |
|---|---|---|
| PAD-001 | P1 acceptance gap; original SGR test | Three supplied white/black/safe-row mouse clicks all report C4 at velocity 0.475, rather than E4/C#4/E4 with distinct velocities. Pure geometry and keyboard tests pass. Investigate renderer/input timing and coordinate mapping; do not claim a physical-terminal defect is already proved. Require real SGR acceptance plus manual Windows Terminal confirmation before closure. |
| PAD-002 | P1 input validation; four xfail cases | Unhashable id/type/target and non-object inputs raise TypeError/AttributeError instead of returning validation diagnostics. Validate structural types before lookup/topological traversal, then add bounded graph-size/depth tests. |
| PAD-PKG-001 | P2 distribution; build log | `setuptools.build_meta.build_wheel()` fails automatic discovery with the multiple top-level `themes` and `patches` directories. Explicit module/data packaging and clean-environment entry-point tests are needed. Source-directory launch is unaffected. |

Coverage includes all factory patches/themes, deterministic rendering, graph ordering/cycles, numeric ranges,
config fallbacks/emergency binding protections, session operations, snapshots, WAV output, command dispatch,
headless keyboard paths and medley generation. Newly added numeric NaN/Inf/bool/string cases return diagnostics.
A zero-duration render deliberately clamps to 0.1 seconds; the review test respects that source policy.

The medley byte-for-byte reproduction is recorded in [medley-reproduction.txt](../../../evidence/medley-reproduction.txt).
No subjective listening decision has been made. Headless acceptance and factory demos are not coverage of
all graph topologies, arbitrary malicious theme data, rapid threaded playback cancellation, or live device latency.

## Publication and physical gates

A passing preservation CI means original hashes and the declared characterization baseline hold.
It does not mean the expected failures were fixed, packaging was certified or playback is safe at arbitrary gain.
Physical audio output, MIDI hardware, real Windows Terminal mouse/drag behaviour, sustained low-latency load,
perceptual quality and operating-system-specific launcher execution remain untested locally.

Build-discovery reference: [setuptools package discovery](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html).
Headless input/output reference: [prompt-toolkit API](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html).
