# Pre-integration peer sign-off markers (historical)

**Archived.** These markers were written by the now-retired foundry team
during rounds 1 through 4; the mechanism that produced them no longer runs
in this repo (see `docs/decisions/015-retire-foundry-operating-model.md`).
They are kept here because decision records 001 through 007 cite specific
markers in this directory as the independently-checkable sign-off evidence
for those decisions. The rest of this file describes the mechanism as it
existed when the markers were written; nothing below is a live instruction.

The first of the review layers: before a doer's slice integrated into the
round branch, a resident that is *not the author* reviews the diff
in-worktree and writes a marker here. **No marker, no integration.**

This project's doer roster is `claude-worker`, `codex-worker`, and
`agy-worker` (three doers; `cursor` is seated read-only as critic,
tiebreaker-only, per `.team/team-config.yaml`), so "not the author" is
two candidates rather than one. The orchestrator names the
reviewer when it dispatches the sign-off. One marker from one non-author
resident clears the gate; more are not required, and an author never picks
its own reviewer.

This is deliberately not the same thing as an external review that posts on
the PR after it opens (if this project has one), and not the same thing as
the consensus decision record (see `docs/decisions/README.md`).
Layer 1 catches problems while the branch is still cheap to change. The other
layers are still required on top of it.

## Filename pattern

    .team/signoffs/<branch-slug>-<short-sha>.md

- `<branch-slug>`: the reviewed branch with `/` replaced by `-`, so
  `claude/caching-strategy` becomes `claude-caching-strategy`.
- `<short-sha>`: the first 12 characters of the reviewed commit SHA.

Example: `.team/signoffs/claude-caching-strategy-9f3a1c4d8e02.md`

The SHA is in the filename on purpose. A marker is evidence about one
specific commit, not a standing blessing of a branch: if the author pushes
more commits after the sign-off, the marker no longer covers the branch head
and the peer reviews again.

## Required contents

Front matter, then a short prose review note:

```markdown
---
reviewed_branch: claude/caching-strategy
reviewed_sha: 9f3a1c4d8e02b7f5a3c1d9e8f7b6a5c4d3e2f1a0
reviewed_by: codex-worker
authored_by: claude-worker
timestamp: 2026-07-16T14:22:05Z
tests_run: tools/run_tests.sh
result: signed-off
---

What the reviewer actually checked, and anything the author changed in
response before this marker was written.
```

Field notes:

- `reviewed_sha` is the full 40-character SHA of the commit reviewed. The
  filename carries a short form for readability; this field is authoritative.
- `reviewed_by` must **not** equal `authored_by`. A resident never signs off
  its own change. Both fields name a resident from the doer roster; check
  them against each other rather than inferring the reviewer by elimination.
- `timestamp` is UTC, ISO 8601, `Z` suffix.
- `tests_run` records the command the reviewer actually ran in the worktree.
  A sign-off is a claim the reviewer ran them, so an honest `tests_run: none`
  beats a decorative entry.
- `result` is `signed-off` or `changes-requested`. Only `signed-off` clears
  the gate. A `changes-requested` marker stays in the repo as history; the
  re-review after the fixes writes a new marker at the new SHA.

## What the reviewer checks

At minimum, before writing `result: signed-off`:

1. The tests run and pass in the worktree.
2. The diff conforms to this project's `AGENTS.md` invariants and its no
   em-dashes style rule.
3. The diff matches the synthesis the team agreed on, rather than the
   author's own preference having drifted back in during implementation.
4. If the diff touches a protected path (`.github/protected-paths.txt`), a
   signed decision record exists to cover it.

A sign-off is a claim that you checked these. Do not write one you did not
earn.
