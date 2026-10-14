# [TRIO-017] Packaging, launchers, documentation, acceptance and release

Work in `techrote/tuisynth` on **TRIO-017** and complete it end-to-end: implementation,
tests, pull request, CI fixes, merge after every automated check is green, then the tag and
release steps below.

## Depends on

- TRIO-010 (#11), TRIO-012 (#13) and TRIO-014 (#15) must be closed.
- TRIO-015 (#16) and TRIO-016 (#17): include them if merged; if still open, list
  them as deferred in the release notes. Do not wait for them.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/10-TESTING-CI-RELEASE.md` (whole file)
4. `trio/docs/programme/IMPLEMENTATION-PROGRAMME.md` section "v0.1 release gate"
5. `trio/docs/rag/00-CHARTER.md` (whole file)
6. `trio/docs/PROVENANCE.md`

## Objective

Make the three instruments installable and launchable by a normal Windows or Linux user,
document them properly, provide the human acceptance checklist, and publish `trio-v0.1.0`
built by CI from the tagged commit.

## Work

1. **Packaging**: confirm every `pyproject.toml` ships its presets and skins; extend
   `tools/check.py --packaging` to run `<name> --selftest` from the clean venv; run it in
   `trio.yml` on pull requests too (not only on push).
2. **Launchers** in `trio/launch/`: `Aurora.cmd`, `Loom.cmd`, `Drift.cmd` (Windows) and
   `aurora.sh`, `loom.sh`, `drift.sh` (POSIX): create `trio/.venv` on first run with
   `requirements-dev.txt` minus pytest/build plus the `audio` and `midi` extras, install the
   four packages from source, then start the instrument passing through arguments. Re-runs
   skip setup. Add `trio/launch/README.md`. Test the POSIX scripts with `bash -n` and the `.cmd`
   files by a CI step on Windows that runs `Aurora.cmd --version` in a scratch copy.
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
5. **Release**: `trio/CHANGELOG.md` (0.1.0 entry listing merged TRIO issues and deferred
   stretch issues); `.github/workflows/trio-release.yml` triggered by tags `trio-v*` that builds
   the four wheels from the tagged commit, runs `--selftest` from a clean venv, and creates a
   GitHub release with the wheels and `CHANGELOG` notes (`permissions: contents: write`).
6. After this PR is merged and `main` CI is green: create and push the annotated tag
   `git tag -a trio-v0.1.0 -m "TRIO v0.1.0" <merged-commit>` and `git push origin trio-v0.1.0`;
   watch `trio-release.yml` until it succeeds; verify the release lists four wheels.

## Tests (names are binding)

- `trio/kit/tests/test_packaging_metadata.py`: package-data globs present; versions equal;
  instrument dependency pins `trio-kit==0.1.0`.
- `trio/kit/tests/test_readmes.py`: keys/mouse tables match `tools/gen_keys.py` output.
- CI: packaging job on both platforms installs wheels in a clean venv and runs all three
  `--selftest`s; Windows launcher smoke step.

## Acceptance criteria

- Every item of the v0.1 release gate satisfied or explicitly deferred (stretch only).
- Release `trio-v0.1.0` exists with four wheels built by the tag workflow.
- No binary or credential committed; `PROVENANCE.md` complete for every merged TRIO PR.

## Out of scope

Bundling Python/executables; PyPI publication.

## Delivery

Follow `trio/AGENTS.md` sections 2-7 for the PR (branch `trio-017-release`), then step 6.
If the release workflow fails, fix it in a follow-up PR under the same contract and retag
only after deleting the failed tag and its draft release.
