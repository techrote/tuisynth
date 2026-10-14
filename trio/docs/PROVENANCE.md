# TRIO provenance ledger

One row per TRIO issue branch, added on that branch before it is squash-merged into local
`main` (see `trio/AGENTS.md` section 4).
Record the tool and the **exact model id the tool reports**. Write `unknown` rather than
guessing. "Human edits" records any change a person made to the agent's output before merge.

| Issue | Branch | Tool and version | Model id | Date | Human edits |
|---|---|---|---|---|---|
| planning | planning PRs #19 and local-workflow update | Claude Code | claude-opus-5-5 | 2026-10-14 | owner-requested plan; no implementation code |
