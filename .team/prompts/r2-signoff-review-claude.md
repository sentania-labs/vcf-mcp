# Fast-lane: peer-review two sign-off marker repairs

You are claude-worker. This is a **fast-lane** assignment: review two small
diffs and write two sign-off markers. No proposal, no critique, no protocol.

## Context

PR #1's external Codex review found that two round-1 sign-off markers had
malformed front matter (`reviewed_at` instead of the required `timestamp`, and
missing `tests_run` and `result`). Their original authors have each repaired
their own marker on a branch:

| Branch | Head | Author | Repairs |
| --- | --- | --- | --- |
| `codex/r2-signoff-fix` | `bf93986a582e291acb779081b6ec046c5cf8bb52` | codex-worker | `.team/signoffs/agy-round1-architecture-0a3665930789.md` |
| `agy/r2-signoff-fix` | `f462682ac6f8c15e37d9304e15b6680662e69989` | agy-worker | `.team/signoffs/claude-round1-architecture-ab2570cef0f1.md` |

Both branch from `round/1-architecture` at `263af83`. You authored neither, so
you are an eligible reviewer for both.

Note that one of them repairs the marker that reviewed *your own* round-1
branch. You are reviewing agy-worker's front-matter repair, not re-opening or
endorsing its review of you. Say so if it matters to your conclusion.

## Your branch

You are already on `claude/r2-signoff-review`, branched from
`round/1-architecture` at `263af83`. Commit there. Do not push. Do not open a
PR.

**Read the two branches without entering their worktrees.** Use `git diff` and
`git show` from your own worktree, exactly as you did when you reviewed
`codex/fix-consensus-selftest` last round. Do not check out, modify, or run
anything inside another resident's worktree.

## What to check

Read `.team/signoffs/README.md` first; it is the authority.

For each of the two diffs:

1. The repaired front matter now satisfies every field the README requires,
   with the field *names* the README specifies.
2. `reviewed_by` still does not equal `authored_by`.
3. `reviewed_sha` still names a commit that is actually integrated into
   `round/1-architecture`. A marker naming a SHA the round branch does not
   contain is not valid evidence.
4. The **prose review note and the conclusion are unchanged**. These were
   supposed to be front-matter repairs on reviews that already happened, not
   fresh reviews and not re-litigated conclusions. If either author rewrote
   its substantive note, changed its finding, or backdated something
   dishonestly, that is a finding: say so and do **not** sign it off.
5. `tests_run` is honest. Both were documentation-only reviews, so `none` is
   the truthful value; a claimed test run would be a finding.
6. The diff touches nothing else. No em-dashes. `Co-authored-by:` trailer
   present.

## What to produce

One sign-off marker per branch, named and formatted per
`.team/signoffs/README.md`, with `reviewed_by: claude-worker` and the correct
`authored_by`. Use the real current time from `date -u` for the `timestamp`
field; do not guess it.

Commit both markers on `claude/r2-signoff-review`.

If either branch fails a check, write no marker for that branch, state the
problem plainly in your report, and commit only the marker for the branch that
passed. A withheld sign-off is a valid and useful outcome. Do not sign off
something you would not defend.

## Constraints

- No em-dashes anywhere, including commit messages. Hard repo rule.
- `Co-authored-by:` trailer naming you on every commit.
- No credentials or lab-specific configuration.

## Done means

Commits on `claude/r2-signoff-review` carrying your markers. Report each
commit SHA and, for each of the two branches, whether you signed it off or
withheld and why.
