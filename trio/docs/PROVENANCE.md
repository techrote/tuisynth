# TRIO provenance ledger

One row per merged TRIO pull request, added by that PR (see `trio/AGENTS.md` section 4).
Record the tool and the **exact model id the tool reports**. Write `unknown` rather than
guessing. "Human edits" records any change a person made to the agent's output before merge.

| Issue | PR | Tool and version | Model id | Date | Human edits |
|---|---|---|---|---|---|
| planning | (this bootstrap PR) | Claude Code | claude-opus-5-5 | 2026-10-14 | owner-requested plan; no implementation code |
