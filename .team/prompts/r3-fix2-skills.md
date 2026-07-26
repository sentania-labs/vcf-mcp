# Fix dispatch: skills slice, one item, a test that does not hold its guarantee

You are agy-worker. You own the skills slice, `agy/r3-skills`, currently at
`88530b39c74270a29f7757619a182e1fb7963f9e`. Your worktree is already checked out
on that branch at that SHA. Work there. Do not create a new branch, do not
rebase, do not push.

claude-worker re-reviewed your slice at `88530b3`. Blocking items 1 and 3 are
**CLOSED with teeth** and nothing regressed. The full marker is in your tree at
`.team/signoffs/agy-r3-skills-88530b39c742.md`; read it, particularly the section
"The test does not hold the guarantee."

Exactly one thing is open. Fix that and nothing else.

## The item

Your sort in `build_index_data` (`skills.py:217`) is **correct, and the reviewer
proved it correct** with a twelve-slug experiment. The implementation half is
done. Do not change the sort.

What is missing is the regression guard.
`test_build_index_data_is_sorted` builds a two-entry tree (`z-skill`, `a-skill`)
and asserts the output order. On this filesystem readdir returns those two
already in alphabetical order, so the assertion passes whether or not the sort
exists. The reviewer deleted the sort line and the suite stayed 8 of 8 green.
That is the exact "green for the wrong reason" pathology the requirement was
written to prevent.

Rewrite that test so it actually holds the guarantee. The reviewer offered two
ways and stated a preference; either is acceptable:

1. Keep the real-tree fixture, but build enough slugs that readdir demonstrably
   scrambles (twelve worked for the reviewer), then assert **both** that
   `slugs == sorted(slugs)` **and** that the raw `Path.iterdir()` order was
   *not* already sorted. The second assertion is the point: it makes the test
   fail loudly if the fixture stops scrambling, instead of going quietly
   vacuous.
2. Take the filesystem out of it entirely: monkeypatch `Path.iterdir` for the
   duration of the test so it yields the slug directories in reverse order, then
   assert the output is sorted. Deterministic on any filesystem. **This is the
   reviewer's stated preference**, and it is the assertion the requirement
   actually wants.

## The acceptance check, and you must actually run it

A test that passes is not evidence. **Perform the mutation yourself:**

1. Delete the sort line at `skills.py:217`.
2. Run `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q`.
3. Confirm your new test **FAILS**. Paste that failure output.
4. Restore the sort line.
5. Re-run the suite and confirm it is green again. Paste that output.

If your new test still passes with the sort deleted, it does not hold the
guarantee and you are not done. Do the mutation in a scratch export
(`git archive HEAD` into `/tmp`) or restore the line carefully; do not commit
the mutated state.

## Scope

Do not touch anything else in the slice. The placeholder-exclusion work and the
digest verification are closed and reviewed; leave them alone.

## Commit

One commit on `agy/r3-skills`. The trailer must be **exactly** this string,
character for character:

    Co-authored-by: agy-worker <agy@team.local>

Not `Antigravity`. The seat name is `agy-worker`.

Report back: the new HEAD SHA, the mutation-failure output, and the restored
green suite output.
