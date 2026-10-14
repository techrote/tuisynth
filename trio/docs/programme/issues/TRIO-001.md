# [TRIO-001] Workspace foundation, packaging skeleton and TRIO CI

Work in `techrote/tuisynth` on **TRIO-001** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

None. The planning documents (`trio/AGENTS.md`, `trio/docs/`) must already be on `main`.

## Read first

1. `trio/AGENTS.md` (whole file) and the repository root `AGENTS.md`
2. This issue and all of its comments
3. `trio/docs/rag/01-ARCHITECTURE.md` (whole file)
4. `trio/docs/rag/10-TESTING-CI-RELEASE.md` sections "Single entry point", "Pinned development
   dependencies", "CI workflow"
5. `.github/workflows/ci.yml` and `requirements-review.txt` (read only; do not modify)

## Objective

Create the `trio/` workspace so that four uniquely named Python distributions install side by
side into one virtual environment, a single command runs all TRIO tests, and a new
path-filtered GitHub Actions workflow tests `trio/` on Linux and Windows.

## Files to create

- `trio/.gitignore`: `.venv/`, `build/`, `dist/`, `*.egg-info/`, `__pycache__/`,
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
- `trio/kit/tests/test_foundation.py`
- `trio/tools/check.py` exactly as specified in TRIO-TEST "Single entry point" (stdlib only;
  `--package` accepts `kit`, `aurora`, `loom`, `drift`, `all`; packages whose folder does not
  exist are skipped with a printed notice; `--packaging` builds wheels into a temporary
  directory, creates a fresh venv, installs the kit wheel and each instrument wheel with
  `--no-index --find-links <tmp>` plus pinned third-party deps from `requirements-dev.txt`,
  then runs `<name> --version` from that venv)
- `.github/workflows/trio.yml` exactly as specified in TRIO-TEST "CI workflow", using the same
  `actions/checkout` and `actions/setup-python` commit SHAs as `.github/workflows/ci.yml`
- Update `trio/README.md` "Development" section with the setup commands below.

Development setup that must work on Windows and Linux:

```sh
python -m venv .venv
# activate it
python -m pip install -r trio/requirements-dev.txt
python -m pip install -e trio/kit -e trio/aurora -e trio/loom -e trio/drift
python trio/tools/check.py --package all
```

## Tests (names are binding)

- `trio/kit/tests/test_foundation.py::test_kit_version_is_semver`
- `trio/kit/tests/test_foundation.py::test_distribution_and_import_names_are_unique`
  (parse the four `pyproject.toml` files with `tomllib`)
- `trio/kit/tests/test_foundation.py::test_instruments_do_not_import_each_other`
  (AST scan of every `.py` under `trio/<name>/src`)
- `trio/<name>/tests/test_cli.py::test_version_flag` and `::test_unknown_invocation_returns_2`

## Acceptance criteria

- All four packages install editable into one venv; `aurora --version`, `loom --version`,
  `drift --version` print the right text.
- `python trio/tools/check.py --package all` and `--packaging` pass locally.
- `TRIO` workflow green on `ubuntu-latest`/3.11 and `windows-latest`/3.14; the existing
  "Synth preservation and review" workflow still green.
- No file outside `trio/`, `.github/workflows/trio.yml` and `trio/docs/PROVENANCE.md` changed.

## Out of scope

Any synth, DSP, UI or MIDI code.

## Delivery

Follow `trio/AGENTS.md` sections 2-7 exactly. Branch `trio-001-foundation`, PR title
`[TRIO-001] Workspace foundation, packaging skeleton and TRIO CI`, body per section 5 with
`Closes #<this issue>`, provenance row, squash-merge only when every check is green.
