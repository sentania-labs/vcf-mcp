# Fast-lane fix: repair your own sign-off marker's front matter

You are codex-worker. This is a **fast-lane** assignment: one mechanical fix,
no protocol, no proposal, no critique. Do exactly this and stop.

## Context

PR #1 (`round/1-architecture`) received its external Codex review. One finding
is against a sign-off marker **you authored** as the reviewer:

> This marker does not satisfy `.team/signoffs/README.md`: it uses
> `reviewed_at` instead of the required `timestamp` and omits both `tests_run`
> and `result`. The README states that only `result: signed-off` clears the
> integration gate, so this is not valid review evidence for the integrated
> agy slice.

The finding is correct. The file is
`.team/signoffs/agy-round1-architecture-0a3665930789.md`. You wrote it
(`reviewed_by: codex-worker`, `authored_by: agy-worker`).

## Your branch

You are already on `codex/r2-signoff-fix`, branched from
`round/1-architecture` at `263af83`. Commit there. Do not push. Do not open a
PR. Do not touch any other branch or worktree.

## What to do

Read `.team/signoffs/README.md` first; it is the authority on the required
fields, not this prompt.

Then repair the front matter of your marker so it satisfies the README:

- Replace the non-standard `reviewed_at` key with the required `timestamp`
  key. **Keep the same time value** (`2026-07-20T23:33:21Z`). That is when you
  actually did the review, and the fix is to the field name, not to the fact.
- Add `tests_run`. The review was documentation-only, as your own prose says.
  Record that honestly (`none`, or whatever the README's guidance indicates
  for a docs-only review). Do not claim you ran a suite you did not run.
- Add `result: signed-off`, which is what you in fact concluded: your prose
  says you found no constitutional violation.

**Do not rewrite the prose review note and do not change your conclusion.**
This is a front-matter repair on a review you already performed. You are not
re-reviewing the agy slice and you must not represent this as a fresh review.
If, and only if, reading the README reveals a further required field that is
also missing, add that too and say so in your commit message.

Check whether `reviewed_sha` still matches `0a3665930789...` on the current
round branch. If the SHA the marker names is no longer the agy commit
integrated into `round/1-architecture`, stop and write a BLOCKED marker per
`.team/blocked/README.md` instead of guessing.

## Constraints

- No em-dashes anywhere, including the commit message. Hard repo rule.
- Your commit carries the `Co-authored-by:` trailer naming you.
- No credentials or lab-specific configuration in anything you write.
- Run `date -u` and use its real output for any timestamp you add for *this*
  commit's own metadata. Do not guess the current time.

## Done means

One commit on `codex/r2-signoff-fix` repairing that one file. Report the
commit SHA. Nothing else in the diff.
