# Fix dispatch: skills slice, trailing whitespace only

You are agy-worker. You own the skills slice, `agy/r3-skills`, currently at
`ed8eabb3c8232fe62933f3f67898976847bc0d9e`. Your worktree is checked out on that
branch. Work there. Do not create a new branch, do not rebase, do not push.

## The one blocking item from the last review is CLOSED

Your monkeypatched `Path.iterdir` test is correct and the orchestrator verified
it the hard way rather than on report: commenting out the sort at
`skills.py:217` makes `test_build_index_data_is_sorted` fail, and restoring it
makes the suite green at 8 of 8. That is exactly the guarantee the reviewer
asked for. Do not change that test or the sort.

## What this dispatch is for

Consistency of standard, not a new requirement invented for you. codex-worker
held the delivery slice to `git diff --check` being clean against its pre-slice
baseline, and delivery was blocked on six trailing-whitespace errors until it
was. The skills slice was never checked the same way, and it has 55:

    git diff --check 33bca5d ed8eabb

Every one of them is a blank line carrying indentation, in
`src/vcf_ops_mcp/skills.py` and `tests/test_skills.py`. One of them,
`tests/test_skills.py:295`, you introduced in `ed8eabb` itself; the rest came in
with `41909bb`.

Strip them. Make each of those lines truly empty. **Do not delete the lines and
shift the code**, and do not reflow, reformat, or otherwise touch a line that is
not on that list. This is a whitespace-only commit and its diff should read as
one.

## Acceptance checks, run both and paste the output

    git diff --check 33bca5d HEAD

Must produce no output and exit 0.

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q

Must stay at 15 passed. Nothing here should move a test. If a test moves, stop
and say so rather than adjusting the test.

Then re-confirm the guarantee still holds, because a whitespace pass touching
`skills.py` is exactly the kind of edit that could disturb it: comment out the
sort at `skills.py:217`, confirm `test_build_index_data_is_sorted` FAILS, restore
it, confirm green. Paste both. Do not commit the mutated state.

## Housekeeping

`commit_msg.txt` is sitting untracked in your worktree from the last dispatch.
It is not committed so it does not affect the branch, but delete it; a reviewer
should not have to work out whether it is scratch or product.

## Commit

One whitespace-only commit on `agy/r3-skills`. The trailer must be **exactly**:

    Co-authored-by: agy-worker <agy@team.local>

Report back: the new HEAD SHA, both acceptance-check outputs, and the
mutation-then-restore outputs.
