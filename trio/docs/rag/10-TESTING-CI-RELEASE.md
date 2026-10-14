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

## Local CI (`trio/tools/ci.py`, created by TRIO-001) - the merge gate

All development and CI run locally inside the development VM; no GitHub access or
credentials are needed. `python trio/tools/ci.py [--lanes preservation,py311,py314]
[--keep-venvs]` reproduces the repository's GitHub workflows:

| Lane | What it runs | Mirrors |
|---|---|---|
| `preservation` | fresh venv from `requirements-review.txt`, then `python tools/validate.py --output trio/.ci/<run>/preservation` (hash checks + the three preserved suites) | `.github/workflows/ci.yml` |
| `py311` | Python 3.11 venv (created with `uv python install 3.11` / `uv venv`), `pip install -r trio/requirements-dev.txt`, editable installs of every existing TRIO package, `python trio/tools/check.py --package all --packaging` | `trio.yml` Linux job |
| `py314` | the same on Python 3.14 | `trio.yml` second job (OS differs: Linux, not Windows) |

- Results go to `trio/.ci/<UTC timestamp>/` (git-ignored): one log per lane plus `summary.json`
  and `summary.md`. The tool prints the summary table and exits non-zero if any lane fails.
- `uv` is preferred for creating the Python 3.11/3.14 interpreters; if `uv` is missing the
  lane falls back to `python3.11`/`python3.14` on `PATH`, and if neither exists the lane is
  reported as **SKIP (interpreter unavailable)**, which counts as a failure for merging.
- Venvs are cached under `trio/.ci/venvs/<lane>-<hash of requirements>` and reused when the
  requirement files are unchanged; `--fresh` rebuilds them.
- **Windows coverage**: the VM is Linux. A Windows lane is run by the orchestrator on the
  Windows host at milestones (after TRIO-008, after each instrument UI, and before
  TRIO-017's tag) with `python trio/tools/ci.py --lanes py311,py314` from an exported copy.
  It is not a per-issue merge gate; Windows failures found there become fixes in the next
  issue or a dedicated follow-up commit.

## GitHub workflow (`.github/workflows/trio.yml`, also created by TRIO-001; not a gate)

Kept so the repository is ready if a human later publishes the local `main` to GitHub. It is
**not executed** during local development. Triggers: `pull_request` and `push` to `main` with
`paths: ["trio/**", ".github/workflows/trio.yml"]`; matrix `ubuntu-latest`/3.11 and
`windows-latest`/3.14; checkout/setup-python pinned to the same SHAs as
`.github/workflows/ci.yml`; steps run `python trio/tools/check.py --package all`
(and `--packaging` on push). TRIO-001 validates its structure with a unit test (parsed as
text; no YAML dependency) but cannot run it.

## Performance gate

`test_performance_budget` per instrument renders 4 s of its densest factory preset with its
maximum polyphony offline and asserts it completes in under **20 s** of wall time on CI
(a deliberately generous gate that only catches pathological per-sample Python loops).
It also prints the realtime factor for information. Real-time headroom is a manual item.

## Golden snapshots

Stored as UTF-8 text in `<package>/tests/snapshots/<screen>-<skin>-<cols>x<rows>.txt`.
Rendering must be deterministic for snapshots: fixed seed, frozen clock, no telemetry
animation (snapshot mode freezes visualizers at a defined frame). Update only with
`--update-snapshots`, and review the diff before merging (note it in the review record).

## Packaging and release (TRIO-017)

- Each `pyproject.toml` uses setuptools with `src/` layout, explicit `package-data` for
  `data/presets/*.json` and `data/skins/*.toml`, a console script, `requires-python >= 3.11`,
  and dependency `trio-kit == <same version>` for instruments.
- Launchers in `trio/launch/`: `Aurora.cmd`, `Loom.cmd`, `Drift.cmd` (Windows) and
  `aurora.sh`, `loom.sh`, `drift.sh` (POSIX). First run creates `trio/.venv` with pinned
  dependencies including the optional audio/MIDI extras, then starts the instrument.
- Version `0.1.0` for all four distributions; annotated tag `trio-v0.1.0` on the local
  `main` merge commit; release notes in `trio/CHANGELOG.md`; wheels built by
  `python trio/tools/ci.py`'s packaging step into `trio/dist/` (git-ignored) from the tagged
  commit and checksummed in `trio/dist/SHA256SUMS`. Publishing a GitHub release is a later,
  human step; `.github/workflows/trio-release.yml` is provided for it but not run locally.
- No WAV, venv, cache, bytecode or credential is ever committed. Offline demo renders are CI
  artifacts only.

## Provenance

Every implementation branch adds one row to `trio/docs/PROVENANCE.md`: issue, branch, agent tool and
version, exact model id as reported by the tool, date, and whether a human edited the result.
If the model id is unknown, write `unknown` - never guess.
