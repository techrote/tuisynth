# TRIO agent execution contract

This file governs every `[TRIO-0NN]` issue. It is written for autonomous coding agents,
including smaller free-tier models. Follow it literally. When something is ambiguous, prefer
the more conservative interpretation and say so in the PR description.

## 1. Authority order

1. Current `main` code, tests and CI configuration.
2. The GitHub issue you are executing, **including all comments**.
3. This file.
4. The RAG documents the issue lists (`trio/docs/rag/`).
5. [`trio/docs/programme/IMPLEMENTATION-PROGRAMME.md`](docs/programme/IMPLEMENTATION-PROGRAMME.md).

The repository root `AGENTS.md` also applies: the folders `cpusynth/`, `padsynth/`,
`niceglitchsynth/` and `evidence/`, plus `tools/validate.py`, `requirements-review.txt`,
`REVIEW.md` and `.github/workflows/ci.yml`, are **preserved and must not be modified**.
You may read them as reference material.

## 2. Before you write code

Run these and read the output:

```sh
git fetch origin
git switch main && git pull --ff-only
gh issue view <N> --comments
gh pr list --state open
gh pr list --state merged --limit 10
```

- Check every issue listed under **Depends on** is **closed** (`gh issue view <dep>`). If one
  is open, stop: comment "Blocked on #<dep>" on your issue and end the task.
- Check no other open PR already works on your issue. If one exists, continue it only if the
  issue comments say so; otherwise stop and comment.
- Read every document under **Read first** in the issue, in order. Do not read the whole
  repository; read the files the issue names, plus the code you are about to change.

## 3. Working rules

- Branch: `trio-0NN-<short-slug>` from current `origin/main`.
- Write or extend tests first for each acceptance criterion, then implement until they pass.
- Run `python trio/tools/check.py --package <pkg>` after each meaningful step and
  `python trio/tools/check.py --package all` before every push. (Before TRIO-001 is merged
  this tool does not exist; TRIO-001 creates it.)
- Keep commits small with messages `TRIO-0NN: <what changed>`.
- Only add dependencies that the issue or `trio/docs/rag/10-TESTING-CI-RELEASE.md` allows.
  Pin exact versions in `trio/requirements-dev.txt` or the package's optional extras.
- Never commit: virtual environments, `__pycache__`, `.pytest_cache`, WAV/FLAC/MP3 files,
  build outputs, user data directories, credentials or tokens.
- Never open real audio or MIDI devices in tests. Never use the network in tests.
- Do not delete, skip, weaken or `xfail` an existing test to make CI pass. If an existing
  test is genuinely wrong, explain why in the PR and get it right instead.
- If a contract in `trio/docs/rag/` must change, change the document in the same PR and call
  it out under "Contract changes" in the PR body.
- Respect the **difference contract** in `trio/docs/rag/00-CHARTER.md`: instrument identity
  stays inside its own package.
- Code style: Python >= 3.11, type hints on public functions, docstrings on public classes,
  no wildcard imports, no global mutable state except module constants.

## 4. Provenance (mandatory)

Add one row to `trio/docs/PROVENANCE.md` in your PR:

`| TRIO-0NN | #<PR> | <tool and version, e.g. opencode 1.19.0> | <exact model id as the tool reports it> | <YYYY-MM-DD> | <human edits: none / describe> |`

If you cannot determine the model id, write `unknown`. Never guess or invent one.

## 5. Pull request

Create the PR with a body containing, in this order:

```markdown
Closes #<issue number>

## Summary
<what was built, in 3-8 bullets>

## Tests
<new/changed tests and the exact command you ran with its final summary line>

## Contract changes
<none, or the RAG document sections you changed and why>

## Skips and limitations
<explicit list: e.g. "real audio device not exercised (CI is device-free)">

## Provenance
<the row you added to PROVENANCE.md>
```

Title: `[TRIO-0NN] <issue title>`. Do not put other `Closes`/`Fixes` keywords in the body.

## 6. CI monitoring, fixing and merging

```sh
git push -u origin HEAD
gh pr create --title "[TRIO-0NN] <title>" --body-file <file>
gh pr checks <PR> --watch --interval 120
```

- Two workflows report on every PR: **Synth preservation and review** (existing) and
  **TRIO** (created by TRIO-001). Every reported check must be green.
- When a check fails: read the failing job log (`gh run view <run-id> --log-failed`), fix the
  cause locally, run `python trio/tools/check.py --package all`, push, and watch again.
- **Fix budget**: at most 6 fix-and-push cycles. If CI is still red after that, or a failure is
  outside your issue's scope (for example a flaky hosted runner or a preserved-folder check
  you did not touch), stop: convert the PR to draft (`gh pr ready --undo <PR>`), comment on the
  issue with the failing check names, log excerpts and what you tried, and end the task.
- Before merging, update your branch if `main` moved: `git fetch origin && git rebase
  origin/main`, re-run checks locally, push with `--force-with-lease`, and wait for green CI.
- Merge only when every check is green and the PR is mergeable:
  `gh pr merge <PR> --squash --delete-branch`.
- After merging: `git switch main && git pull --ff-only && python trio/tools/check.py --package all`,
  then confirm the `push` CI run on `main` succeeds (`gh run list --branch main --limit 2`).
  If main is red because of your merge, open a follow-up fix PR immediately using this same
  contract.
- The issue closes automatically from `Closes #N`. If it did not, close it with a comment
  linking the merged PR.

## 7. Stop conditions (comment on the issue and end the task, do not merge)

- A dependency issue is still open.
- The issue's acceptance criteria conflict with a RAG contract or with merged code and the
  conflict cannot be resolved by a small, documented contract change.
- You would need to modify a preserved folder or file.
- You would need credentials, paid services, hardware or network access in tests.
- The fix budget is exhausted.

## 8. Free-tier model guidance

- Keep your working context small: the issue, this file, the listed RAG sections and the
  files you edit. Summarise long tool output instead of re-reading it.
- Prefer simple, explicit code over clever abstractions. Follow the exact names, signatures
  and file paths given in the issue.
- After every test run, read the **first** failure fully before changing anything.
- If you are unsure whether something is in scope, it is not; note it under "Skips and
  limitations".
