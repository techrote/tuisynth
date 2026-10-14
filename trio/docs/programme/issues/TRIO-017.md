# [TRIO-017] Packaging, launchers, documentation, acceptance and release

Work in your local clone of `techrote/tuisynth` on **TRIO-017** and complete it end-to-end with the
local workflow in `trio/AGENTS.md`, then the local tag and release steps below.

## Depends on

- TRIO-010 (#11), TRIO-012 (#13) and TRIO-014 (#15) must be `done` in `trio/docs/programme/STATUS.md`.
- TRIO-015 (#16) and TRIO-016 (#17): include them if `done`; otherwise list them as deferred
  in the release notes. Do not wait for them.

## Read first

1. `trio/AGENTS.md`
2. This issue file (`trio/docs/programme/issues/TRIO-017.md`) and its row in `STATUS.md`
3. `trio/docs/rag/10-TESTING-CI-RELEASE.md` (whole file)
4. `trio/docs/programme/IMPLEMENTATION-PROGRAMME.md` section "v0.1 release gate"
5. `trio/docs/rag/00-CHARTER.md` (whole file)
6. `trio/docs/PROVENANCE.md`

## Objective

Make the three instruments installable and launchable by a normal Windows or Linux user,
document them properly, provide the human acceptance checklist, and produce a local
`trio-v0.1.0` release: tag plus wheels built by local CI from the tagged commit.

## Work

1. **Packaging**: confirm every `pyproject.toml` ships its presets and skins; extend
   `tools/check.py --packaging` to run `<name> --selftest` from the clean venv; make sure
   `tools/ci.py` runs packaging in both Python lanes; keep `trio.yml` running it on pull requests
   too (for later publication).
2. **Launchers** in `trio/launch/`: `Aurora.cmd`, `Loom.cmd`, `Drift.cmd` (Windows) and
   `aurora.sh`, `loom.sh`, `drift.sh` (POSIX): create `trio/.venv` on first run with
   `requirements-dev.txt` minus pytest/build plus the `audio` and `midi` extras, install the
   four packages from source, then start the instrument passing through arguments. Re-runs
   skip setup. Add `trio/launch/README.md`. Test the POSIX scripts with `bash -n` plus a local CI
   smoke step running `aurora.sh --version` in a scratch copy. The `.cmd` launchers are checked by
   the orchestrator's Windows-host milestone lane (record the result in the review record, or
   "not run").
3. **Documentation**: `trio/README.md` (what TRIO is, screenshots as `--snapshot` text blocks
   for each instrument's main screen, install/launch, troubleshooting: no audio device, no
   MIDI, Windows Terminal mouse settings); one `README.md` per instrument with keys and mouse
   tables generated from the actual bindings (add a small script `tools/gen_keys.py` and a test
   that the README tables match it), skins list, presets list.
4. **Acceptance checklist** `trio/docs/ACCEPTANCE.md`: per instrument, steps for a human on
   Windows Terminal with a real audio device and a USB MIDI keyboard (launch, every mouse
   gesture, on-screen keyboard note-off, computer keyboard gates/latch, MIDI notes/sustain/
   bend/mod/CC-learn, skin switching, presets save/load, 10-minute stability, CPU reading,
   listening notes) with an empty results table. CI must not fill it in.
5. **Release files**: `trio/CHANGELOG.md` (0.1.0 entry listing `done` TRIO issues and deferred
   stretch issues); `trio/tools/release.py` that, from a clean checkout of a given tag, builds the
   four wheels into `trio/dist/trio-v0.1.0/`, installs them into a fresh venv, runs every
   `--selftest`, and writes `SHA256SUMS`; and `.github/workflows/trio-release.yml` (for later
   publication, not run locally) that does the same on a pushed `trio-v*` tag and creates a
   GitHub release.
6. After the squash-merge into local `main` and green post-merge `ci.py`: create the annotated
   tag `git tag -a trio-v0.1.0 -m "TRIO v0.1.0"` on that commit, run
   `python trio/tools/release.py trio-v0.1.0`, and paste its summary and `SHA256SUMS` into the
   review record. Do not push anything.

## Tests (names are binding)

- `trio/kit/tests/test_packaging_metadata.py`: package-data globs present; versions equal;
  instrument dependency pins `trio-kit==0.1.0`.
- `trio/kit/tests/test_readmes.py`: keys/mouse tables match `tools/gen_keys.py` output.
- CI: packaging job on both platforms installs wheels in a clean venv and runs all three
  `--selftest`s; Windows launcher smoke step.

## Acceptance criteria

- Every item of the v0.1 release gate satisfied or explicitly deferred (stretch only).
- Local tag `trio-v0.1.0` exists; `trio/dist/trio-v0.1.0/` holds four wheels and `SHA256SUMS`
  produced by `release.py` (git-ignored, not committed).
- No binary or credential committed; `PROVENANCE.md` complete for every `done` TRIO issue.

## Out of scope

Bundling Python/executables; PyPI or GitHub publication (a later human step).

## Delivery

Follow `trio/AGENTS.md` sections 2-7 (branch `trio-017-release`), then step 6. If `release.py`
fails, fix it on a follow-up branch under the same contract, delete the local tag
(`git tag -d trio-v0.1.0`) and retag the new merge commit.
