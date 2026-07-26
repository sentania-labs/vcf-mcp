# Fix dispatch: delivery slice, two mechanical Tier 1 items

You are agy-worker. You own the delivery slice, `agy/r3-delivery`, currently at
`11b0227e9dd22ccc7bf44330d4a97ab077684b3a`. Your worktree is already checked out
on that branch at that SHA. Work there. Do not create a new branch, do not
rebase, do not push.

codex-worker re-reviewed your slice at `11b0227` and requested changes on
**exactly two items**, both mechanical. The full marker is in your tree at
`.team/signoffs/agy-r3-delivery-11b0227e9dd2.md`; read it. Four of the five
Tier 1 items are CLOSED and nothing about them is reopened here.

Do these two things and nothing else. Do not fix the Tier 2 remainders in this
commit; they are the next increment's worklist and are deliberately out of scope.

## Item 1: restore eleven baseline files your cleanup deleted

Your removal of the 45 slice-local artifacts introduced by `19efb0c` was
**correct and must stay removed**. Do not undo it.

But the same cleanup also deleted eleven files that already existed at the
pre-slice baseline `33bca5d`. They are not yours to delete. Restore them at
their baseline content:

```text
.team/markers/orchestrator-run-20260720-223456-end.md
.team/markers/orchestrator-run-20260720-223456-start.md
.team/markers/orchestrator-run-20260720-224036-end.md
.team/markers/orchestrator-run-20260720-224036-start.md
.team/markers/orchestrator-run-20260720-231633-end.md
.team/markers/orchestrator-run-20260720-231633-start.md
.team/markers/stale/agy-DUPLICATE-proposal-77c681e.md
.team/markers/stale/r1p1-agy-20260720-224217-start.KILLED-DUPLICATE.md
.team/markers/stale/r1p1-claude-20260720-224213-start.KILLED-DUPLICATE.md
.team/markers/stale/r1p1-codex-20260720-224215-start.KILLED-DUPLICATE.md
.team/markers/vom-r2-esc-20260721-171423-start.md
```

`git checkout 33bca5d -- <path>` for each is the direct way.

**Acceptance check, run it and paste the output in your commit or report:**

    git diff --diff-filter=D --name-only 33bca5d HEAD

That must list only slice-local artifacts introduced by `19efb0c`, and none of
the eleven above.

## Item 2: six trailing-whitespace errors

`git diff --check 19efb0c..11b0227` currently reports six:

```text
.team/markers/r3-delivery-20260725-234637-end.md:20
.team/markers/r3-delivery-20260725-234637-end.md:23
.team/markers/vom-r3-fix-delivery-20260726-005457-start.md:11
.team/markers/vom-r3-fix-delivery-20260726-005457-start.md:16
src/vcf_ops_mcp/app.py:60
tests/test_admin.py:23
```

Strip the trailing whitespace. The two source ones (`app.py:60`,
`tests/test_admin.py:23`) are blank lines carrying indentation; make them truly
empty, do not delete the lines and shift the code.

The four in `.team/markers/` are dispatcher-generated marker files with empty
`model:` and `injected_secret_keys:` values. Strip the trailing space after the
colon; do not otherwise alter a marker's recorded content, and do not delete the
marker files.

**Acceptance check:**

    git diff --check 19efb0c..HEAD

Must produce no output and exit 0.

## Before you commit

Run the suite in your worktree and paste the result:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q

Nothing in this change should move a test. If a test moves, stop and say so
rather than adjusting the test.

## Commit

One commit on `agy/r3-delivery`. The message names both items. The trailer must
be **exactly** this string, character for character:

    Co-authored-by: agy-worker <agy@team.local>

Not `Antigravity`. The seat name is `agy-worker`.

Report back: the new HEAD SHA, the output of both acceptance checks, and the
suite result.
