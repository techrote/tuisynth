---
corpus: tuisynth
programme: trio
document_id: TRIO-TEST
status: authority
---
# Testing, CI, packaging and release contract

## Test layers

1. **Pure unit tests**: params, presets, events, MIDI parsing, keyboard piano, skin
   validation, geometry/hit maps, formatting.
2. **Offline DSP tests** with NumPy assertions on rendered audio from `OfflineEngine`
   (spectra, pitch, decay, statistics, limiter, finiteness, determinism).
3. **Headless TUI tests** with `trio_kit.tui.testing.HeadlessApp`: real key sequences and SGR
   mouse byte sequences through prompt_toolkit pipe input; golden screen snapshots.
4. **Packaging tests**: build wheels and install them into a fresh virtual environment
   outside the source tree, then run `<cli> --version` and `<cli> --selftest`.
5. **Manual acceptance** (not CI): real audio device, USB MIDI device, Windows Terminal
   mouse/keyboard, listening. Recorded by a human in `docs/ACCEPTANCE.md`.

Rules: never open an audio or MIDI device in tests; never `time.sleep` for more than 50 ms in a
unit test (inject clocks); no network in tests; tests must pass on Linux and Windows.
A capability that cannot run in CI is reported as an explicit `pytest.skip` with a reason,
never as a pass. Do not delete, weaken or `xfail` a failing test to get green; fix the code or
stop and report (see `trio/AGENTS.md`).

## Single entry point

`python trio/tools/check.py [--package kit|aurora|loom|drift|all] [--packaging] [--update-snapshots]`

- Runs `python -m pytest -q <package>/tests` for each selected package in its own subprocess.
- `--packaging` builds each selected wheel with `python -m build --wheel` (or
  `pip wheel --no-deps`) into a temp dir, creates a fresh venv, installs kit + package wheels,
  and runs `--version` and `--selftest`.
- Exit code is non-zero if anything fails. Prints a short summary table at the end.

## Pinned development dependencies (`trio/requirements-dev.txt`)

Start from the versions already proven in this repository's CI (`requirements-review.txt`):
`numpy==2.3.5`, `scipy==1.17.0`, `prompt-toolkit==3.0.53`, `wcwidth==0.8.3`,
`pytest==9.0.2`, plus an exact pin for `build` chosen at implementation time. Python >= 3.11
is required, so TOML is read with the standard-library `tomllib`. Optional runtime extras
`sounddevice` and `python-rtmidi` are pinned in each package's `[project.optional-dependencies]`
after checking current stable versions on PyPI at implementation time; they are **not**
installed in CI.

## CI workflow (`.github/workflows/trio.yml`, created by TRIO-001)

- Triggers: `pull_request` and `push` to `main`, with `paths: ["trio/**",
  ".github/workflows/trio.yml"]`.
- Matrix: `ubuntu-latest` / Python 3.11 and `windows-latest` / Python 3.14 (matching the
  existing preservation workflow), `fail-fast: false`, timeout 20 minutes,
  `permissions: contents: read`.
- Steps: checkout and setup-python pinned to the **same commit SHAs** used in
  `.github/workflows/ci.yml`; `pip install -r trio/requirements-dev.txt`;
  `pip install -e trio/kit` plus every instrument that exists; `python trio/tools/check.py
  --package all`; on `push` to main also `--packaging`.
- The existing `ci.yml` ("Synth preservation and review") also runs on every PR and must stay
  green. A TRIO PR is mergeable only when **every** check reported on the PR is green.

## Performance gate

`test_performance_budget` per instrument renders 4 s of its densest factory preset with its
maximum polyphony offline and asserts it completes in under **20 s** of wall time on CI
(a deliberately generous gate that only catches pathological per-sample Python loops).
It also prints the realtime factor for information. Real-time headroom is a manual item.

## Golden snapshots

Stored as UTF-8 text in `<package>/tests/snapshots/<screen>-<skin>-<cols>x<rows>.txt`.
Rendering must be deterministic for snapshots: fixed seed, frozen clock, no telemetry
animation (snapshot mode freezes visualizers at a defined frame). Update only with
`--update-snapshots`, and review the diff in the PR.

## Packaging and release (TRIO-017)

- Each `pyproject.toml` uses setuptools with `src/` layout, explicit `package-data` for
  `data/presets/*.json` and `data/skins/*.toml`, a console script, `requires-python >= 3.11`,
  and dependency `trio-kit == <same version>` for instruments.
- Launchers in `trio/launch/`: `Aurora.cmd`, `Loom.cmd`, `Drift.cmd` (Windows) and
  `aurora.sh`, `loom.sh`, `drift.sh` (POSIX). First run creates `trio/.venv` with pinned
  dependencies including the optional audio/MIDI extras, then starts the instrument.
- Version `0.1.0` for all four distributions; tag `trio-v0.1.0` on the merged main commit;
  GitHub release notes generated from `trio/CHANGELOG.md`; wheels attached by a tag-triggered
  workflow that rebuilds from the tagged commit (never from a developer machine).
- No WAV, venv, cache, bytecode or credential is ever committed. Offline demo renders are CI
  artifacts only.

## Provenance

Every implementation PR adds one row to `trio/docs/PROVENANCE.md`: issue, PR, agent tool and
version, exact model id as reported by the tool, date, and whether a human edited the result.
If the model id is unknown, write `unknown` - never guess.
