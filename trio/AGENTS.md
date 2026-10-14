# TRIO agent execution contract (local workflow)

This file governs every `[TRIO-0NN]` issue. It is written for autonomous coding agents,
including smaller local and free-tier models. Follow it literally. When something is
ambiguous, prefer the more conservative interpretation and record it in your review record.

**Everything happens locally.** Agents work in a local clone inside the development VM,
run CI locally, review and squash-merge into the local `main` branch. Agents never push,
never open pull requests, never call the GitHub API and never need credentials. Publishing to
GitHub, if wanted, is a separate step done later by a human.

## 1. Authority order

1. Current local `main` code, tests and `trio/tools/ci.py`.
2. The issue file you are executing: `trio/docs/programme/issues/TRIO-0NN.md`, plus any
   notes for it in `trio/docs/programme/STATUS.md`.
3. This file.
4. The RAG documents the issue lists (`trio/docs/rag/`).
5. [`trio/docs/programme/IMPLEMENTATION-PROGRAMME.md`](docs/programme/IMPLEMENTATION-PROGRAMME.md).

(The same issues exist on GitHub as `techrote/tuisynth` #2-#18 for reference; the local issue
files are what you execute.)

The repository root `AGENTS.md` also applies: the folders `cpusynth/`, `padsynth/`,
`niceglitchsynth/` and `evidence/`, plus `tools/validate.py`, `requirements-review.txt`,
`REVIEW.md` and `.github/workflows/ci.yml`, are **preserved and must not be modified**.
You may read them as reference material.

## 2. Before you write code

```sh
cd ~/workspace/tuisynth
git status                      # must be clean; if not, stop and report
git switch main
git log --oneline -5
cat trio/docs/programme/STATUS.md
cat trio/docs/programme/issues/TRIO-0NN.md
```

- Every issue under **Depends on** must have status `done` in `STATUS.md`. If one is not,
  stop (section 7).
- If `STATUS.md` shows your issue `in-progress` with a branch name, continue that branch
  (`git switch <branch>`) instead of starting over.
- Read every document under **Read first** in the issue, in order. Do not read the whole
  repository; read the files the issue names, plus the code you are about to change.
- Set your row in `STATUS.md` to `in-progress` with your branch name in the first commit.

## 3. Working rules

- Branch: `trio-0NN-<short-slug>` from current local `main`.
- Write or extend tests first for each acceptance criterion, then implement until they pass.
- Run `python trio/tools/check.py --package <pkg>` after each meaningful step and
  `python trio/tools/check.py --package all` before every commit. (Before TRIO-001 is merged
  these tools do not exist; TRIO-001 creates them.)
- Keep commits small with messages `TRIO-0NN: <what changed>`.
- Only add dependencies that the issue or `trio/docs/rag/10-TESTING-CI-RELEASE.md` allows.
  Pin exact versions in `trio/requirements-dev.txt` or the package's optional extras.
- Never commit: virtual environments, `__pycache__`, `.pytest_cache`, `trio/.ci/` results,
  WAV/FLAC/MP3 files, build outputs, user data directories, credentials or tokens.
- Never open real audio or MIDI devices in tests. Tests must not use the network.
- Do not delete, skip, weaken or `xfail` an existing test to make CI pass. If an existing
  test is genuinely wrong, explain why in the review record and correct it.
- If a contract in `trio/docs/rag/` must change, change the document in the same branch and
  list it under "Contract changes" in the review record.
- Respect the **difference contract** in `trio/docs/rag/00-CHARTER.md`: instrument identity
  stays inside its own package.
- Code style: Python >= 3.11, type hints on public functions, docstrings on public classes,
  no wildcard imports, no global mutable state except module constants.

## 4. Provenance (mandatory)

Add one row to `trio/docs/PROVENANCE.md` on your branch:

`| TRIO-0NN | <branch> | <tool and version, e.g. opencode 1.19.0> | <exact model id as the tool reports it, e.g. lmstudio/qwen3.8-27b> | <YYYY-MM-DD> | <human edits: none / describe> |`

The orchestrator tells you which model you are running as; if you cannot determine it, write
`unknown`. Never guess or invent one.

## 5. Review record (replaces the pull request)

Create `trio/docs/programme/reviews/TRIO-0NN.md` on your branch:

```markdown
# TRIO-0NN review record

## Summary
<what was built, in 3-8 bullets>

## Tests
<new/changed tests and the exact command you ran with its final summary line>

## Local CI
<the final `python trio/tools/ci.py` summary table, pasted verbatim>

## Self-review
- [ ] every acceptance criterion in the issue is met (list any not met)
- [ ] no preserved file changed (`git diff --stat main...HEAD`)
- [ ] no generated files, binaries or secrets committed
- [ ] difference contract respected
- [ ] docs/RAG updated for any contract change

## Contract changes
<none, or the RAG document sections you changed and why>

## Skips and limitations
<explicit list: e.g. "real audio device not exercised (CI is device-free)", "Windows lane not run">

## Provenance
<the row you added to PROVENANCE.md>
```

If the orchestrator runs an independent review with a second model (the review gate in
section 6), its findings are appended under `## Independent review` and must be fixed (or
explicitly answered) before merging.

**Reviewer instructions** (when you are the reviewer): do not edit code. Read the issue file,
this file and `git diff main...<branch>`; check every acceptance criterion, the binding test
names, preserved paths, the difference contract and the review record's claims. Append
`## Independent review` with numbered findings (`blocking` or `minor`, file:line, what and
why) or `No findings.`, plus a line `Reviewer: <tool> <model id>`. Commit it on the branch as
`TRIO-0NN: independent review`, then print exactly `TRIO_REVIEWED TRIO-0NN <n blocking>`.

## 6. Local CI, fixing and merging

`python trio/tools/ci.py` is the merge gate. It reproduces the repository's GitHub workflows
locally (see `trio/docs/rag/10-TESTING-CI-RELEASE.md` "Local CI"): the preserved-synth
validation lane and the TRIO lanes on Python 3.11 and 3.14. It prints a summary table and exits
non-zero if any lane fails.

1. Commit your work on the branch, including the `STATUS.md` row (still `in-progress`),
   the `PROVENANCE.md` row and the review record.
2. Bring the branch up to date: `git rebase main`.
3. Run `python trio/tools/ci.py`. When a lane fails, read its log under `trio/.ci/<run>/`, fix the
   cause, commit, and run it again.
4. **Fix budget**: at most 6 fix-and-rerun cycles. If CI is still red, or a failure is outside
   your issue's scope, stop (section 7).
   **Review gate**: if your prompt says `REVIEW_BEFORE_MERGE`, stop here once every lane
   passes: commit, print exactly `TRIO_READY_FOR_REVIEW TRIO-0NN` and end the task. A
   reviewer model then appends `## Independent review` to your review record. When you are
   restarted, fix or answer every finding (write the answer under each finding), rerun
   `python trio/tools/ci.py` (the fix budget continues), and go on with step 5.
5. When every lane passes: set your `STATUS.md` row to `done` with today's date and model id,
   update the review record's "Local CI" section, commit, then merge:

   ```sh
   git switch main
   git merge --squash trio-0NN-<slug>
   git commit -m "[TRIO-0NN] <issue title>"
   python trio/tools/ci.py          # post-merge verification on main
   ```

6. If post-merge CI on `main` fails, fix it immediately on `main` within the same fix budget
   (commit `TRIO-0NN: fix post-merge CI`). If you cannot, `git revert --no-edit HEAD`, set your
   row to `blocked` with the reason, commit, and stop.
7. Keep the branch (do not delete it) so the work can be inspected later.
8. Print exactly `TRIO_DONE TRIO-0NN` when finished.

## 7. Stop conditions (record, do not merge)

Set your `STATUS.md` row to `blocked` with a one-line reason, write details under
`## Blocked` in your review record, commit on your branch, print
`TRIO_STOPPED TRIO-0NN <reason>`, and end the task when:

- a dependency issue is not `done`;
- the issue's acceptance criteria conflict with a RAG contract or with merged code and the
  conflict cannot be resolved by a small, documented contract change;
- you would need to modify a preserved folder or file;
- you would need credentials, paid services, hardware, or network access in tests;
- the fix budget is exhausted.

## 8. Model guidance (local and free-tier models)

The model roster, LM Studio settings and OpenCode configuration are in
`trio/docs/rag/12-LOCAL-WORKFLOW-AND-MODELS.md`.

- Keep your working context small: the issue, this file, the listed RAG sections and the
  files you edit. Summarise long tool output instead of re-reading it.
- Prefer simple, explicit code over clever abstractions. Follow the exact names, signatures
  and file paths given in the issue.
- After every test run, read the **first** failure fully before changing anything.
- If you are unsure whether something is in scope, it is not; note it under "Skips and
  limitations".
- Commit often: an interrupted session can be resumed from the branch and `STATUS.md`.
