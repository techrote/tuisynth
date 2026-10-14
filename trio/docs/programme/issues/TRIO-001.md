# [TRIO-001] Workspace foundation, packaging skeleton and TRIO CI

Work in your local clone of `techrote/tuisynth` on **TRIO-001** and complete it end-to-end with
the local workflow in `trio/AGENTS.md`. This issue creates the local CI tool itself, so its merge
gate is the new `python trio/tools/ci.py`, run as the last step before merging.

## Depends on

None. The planning documents (`trio/AGENTS.md`, `trio/docs/`) must already be on local `main`.

## Read first

1. `trio/AGENTS.md` (whole file) and the repository root `AGENTS.md`
2. This issue file (`trio/docs/programme/issues/TRIO-001.md`) and its row in `STATUS.md`
3. `trio/docs/rag/01-ARCHITECTURE.md` (whole file)
4. `trio/docs/rag/10-TESTING-CI-RELEASE.md` sections "Single entry point", "Pinned development
   dependencies", "Local CI", "GitHub workflow"
5. `.github/workflows/ci.yml`, `tools/validate.py` and `requirements-review.txt` (read only; do
   not modify)

## Objective

Create the `trio/` workspace so that four uniquely named Python distributions install side by
side into one virtual environment, one command runs all TRIO tests, and one command runs the
full local CI that reproduces the repository's GitHub workflows inside the development VM.

## Files to create

- `trio/.gitignore`: `.venv/`, `.ci/`, `build/`, `dist/`, `*.egg-info/`, `__pycache__/`,
  `.pytest_cache/`, `*.wav`
- `trio/requirements-dev.txt`: `numpy==2.3.5`, `scipy==1.17.0`, `prompt-toolkit==3.0.53`,
  `wcwidth==0.8.3`, `pytest==9.0.2`, and `build==<current stable, exact pin>`
- `trio/kit/pyproject.toml`: setuptools, name `trio-kit`, version `0.1.0`,
  `requires-python = ">=3.11"`, dependencies `numpy`, `scipy`, `prompt_toolkit`, `wcwidth`
  (lower bounds only), optional extras `audio = ["sounddevice==<pin>"]`,
  `midi = ["python-rtmidi==<pin>"]` (check PyPI for current stable versions), `src/` layout,
  `[tool.setuptools.package-data]` placeholder for `trio_kit` data
- `trio/kit/src/trio_kit/__init__.py` with `__version__ = "0.1.0"`
- For each of `aurora`, `loom`, `drift`:
  - `trio/<name>/pyproject.toml`: name `trio-<name>`, version `0.1.0`, dependency
    `trio-kit==0.1.0`, console script `<name> = "trio_<name>.__main__:main"`, package data
    globs `data/presets/*.json` and `data/skins/*.toml`
  - `trio/<name>/src/trio_<name>/__init__.py` with `__version__` and `INSTRUMENT_ID = "<name>"`
  - `trio/<name>/src/trio_<name>/__main__.py`: `def main(argv: list[str] | None = None) -> int`
    using `argparse`; supports `--version` (prints `<name> 0.1.0`, returns 0) and `--help`;
    any other invocation prints "not implemented yet" to stderr and returns 2. `if __name__ ==
    "__main__": raise SystemExit(main())`.
  - `trio/<name>/src/trio_<name>/data/presets/.keep` and `data/skins/.keep`
  - `trio/<name>/tests/test_cli.py`
- `trio/kit/tests/test_foundation.py` and `trio/kit/tests/test_ci_tool.py`
- `trio/tools/check.py` exactly as specified in TRIO-TEST "Single entry point" (stdlib only;
  `--package` accepts `kit`, `aurora`, `loom`, `drift`, `all`; packages whose folder does not
  exist are skipped with a printed notice; `--packaging` builds wheels into a temporary
  directory, creates a fresh venv, installs the kit wheel and each instrument wheel with
  `--no-index --find-links <tmp>` plus pinned third-party deps from `requirements-dev.txt`,
  then runs `<name> --version` from that venv)
- `trio/tools/ci.py` exactly as specified in TRIO-TEST "Local CI" (stdlib only): lanes
  `preservation`, `py311`, `py314`; results under `trio/.ci/<UTC timestamp>/` with per-lane
  logs, `summary.json` and `summary.md`; cached venvs under `trio/.ci/venvs/`; options
  `--lanes`, `--fresh`, `--keep-venvs`; exit code non-zero if any lane fails or is skipped.
  The `preservation` lane passes `--output trio/.ci/<run>/preservation` to
  `tools/validate.py` so nothing is written into the preserved `evidence/` folder.
- `.github/workflows/trio.yml` as specified in TRIO-TEST "GitHub workflow" (publication-ready;
  not run locally), using the same `actions/checkout` and `actions/setup-python` commit SHAs as
  `.github/workflows/ci.yml`
- Update `trio/README.md` "Development" section with the commands below.

Development setup that must work on Linux (the VM) and Windows (the host):

```sh
python3 -m venv .venv            # on Windows: python -m venv .venv
# activate it
python -m pip install -r trio/requirements-dev.txt
python -m pip install -e trio/kit -e trio/aurora -e trio/loom -e trio/drift
python trio/tools/check.py --package all
uv python install 3.11 3.14      # once, so ci.py can build its lanes
python trio/tools/ci.py
```

## Tests (names are binding)

- `trio/kit/tests/test_foundation.py::test_kit_version_is_semver`
- `trio/kit/tests/test_foundation.py::test_distribution_and_import_names_are_unique`
  (parse the four `pyproject.toml` files with `tomllib`)
- `trio/kit/tests/test_foundation.py::test_instruments_do_not_import_each_other`
  (AST scan of every `.py` under `trio/<name>/src`)
- `trio/kit/tests/test_foundation.py::test_github_workflow_mirrors_local_lanes` (read
  `.github/workflows/trio.yml` as text: path filters, both matrix entries and the action SHAs
  from `ci.yml` are present)
- `trio/kit/tests/test_ci_tool.py::test_summary_written_and_exit_code` (run `ci.py` with a fake
  lane registry injected through a function argument: one passing and one failing lane) and
  `::test_missing_interpreter_is_skip_and_fails`
- `trio/<name>/tests/test_cli.py::test_version_flag` and `::test_unknown_invocation_returns_2`

## Acceptance criteria

- All four packages install editable into one venv; `aurora --version`, `loom --version`,
  `drift --version` print the right text.
- `python trio/tools/check.py --package all --packaging` passes.
- `python trio/tools/ci.py` passes all three lanes in the VM.
- No file outside `trio/` and `.github/workflows/trio.yml` changed (the `STATUS.md`,
  `PROVENANCE.md` and review-record updates are inside `trio/`), and nothing was written to
  `evidence/`.

## Out of scope

Any synth, DSP, UI or MIDI code.

## Delivery

Follow `trio/AGENTS.md` sections 2-7 exactly. Branch `trio-001-foundation`. Review record
`trio/docs/programme/reviews/TRIO-001.md`. Squash-merge into local `main` only when
`python trio/tools/ci.py` is green.
