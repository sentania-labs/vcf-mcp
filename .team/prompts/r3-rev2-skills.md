# Re-review: skills slice, `agy/r3-skills`

You are claude-worker. You are the peer reviewer. You did not author this slice;
agy-worker did. Do not fix anything you find. Your product is one sign-off
marker.

## What you are reviewing

Branch `agy/r3-skills`. Resolve its current head yourself with
`git rev-parse agy/r3-skills` and review that exact SHA; two commits have landed
since you last looked at `88530b3`, and your marker must name the head you
actually reviewed.

The author's worktree is `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-agy2`.
Read it and run tests there if you like, but **treat it as read-only**: change
nothing, and confirm `git status --porcelain --untracked-files=no` is empty there
when you finish. Commit your marker in your own worktree, on your own branch
`claude/r3-rev-skills`.

## Scope

Your re-review at `88530b3` closed blocking items 1 and 3 with teeth and held on
one half of item 2: the sort was correct but
`test_build_index_data_is_sorted` could not detect the sort's removal, because
the two-entry `z-skill`/`a-skill` fixture came back from readdir already sorted.

Two commits since then:

1. The author took **your stated preference**, option 2: monkeypatch
   `Path.iterdir` for the duration of the test to yield the slug directories in
   reverse order, then assert the output is sorted.
2. A whitespace-only commit stripping trailing whitespace from blank lines in
   `src/vcf_ops_mcp/skills.py` and `tests/test_skills.py`. This was the
   orchestrator's call, for symmetry with the standard codex-worker held the
   delivery slice to, not a defect you raised.

Items 1 and 3 are closed and are **not** reopened here. The non-blocking note you
made about `catalog.current` carrying the placeholder slug is a forward-facing
item for the delivery slice and is recorded; it is not this slice's defect and
is out of scope.

## Named claims to confirm or deny

The orchestrator ran the first two before dispatching you and got the results
shown. **Do not take them on report. Re-run them.** Withholding on any claim is
valid, and "I could not check this" beats a confirmation you did not earn.

1. **The mutation now fails.** Commenting out or deleting `catalog.sort` at
   `skills.py:217` makes `test_build_index_data_is_sorted` FAIL. This is the
   whole point of the item; run it yourself, in a scratch `git archive` export
   under `/tmp`, never in the author's tree.
2. **Restoring the sort makes the suite green again**, 8 of 8 in
   `tests/test_skills.py` and 15 of 15 overall.
3. The monkeypatch is correctly scoped: it is undone after the test (via the
   `monkeypatch` fixture, not a manual restore), and it does not leak into other
   tests. Confirm the suite is order-independent, for instance by running
   `tests/test_skills.py` alone and as part of the whole suite.
4. The monkeypatch intercepts `Path.iterdir` for the **skills directory** and
   passes through for every other path, so it is not masking a real failure
   elsewhere in the call.
5. The sort at `skills.py:217` is byte-identical to what you verified at
   `88530b3`. The whitespace commit did not disturb it.
6. The whitespace commit is genuinely whitespace-only: `git diff -w` between the
   two commits is empty, no line was deleted and no code shifted.
7. `git diff --check 33bca5d <head>` produces no output and exits 0.
8. Blocking items 1 and 3 have not regressed. In particular the placeholder is
   still refused by all four render paths, and the digest is still verified ahead
   of the `continue`.
9. `skills/index.json` still regenerates byte-identical to the committed file,
   twice running, so a regenerate-and-diff CI check stays safe.
10. The trailers on both new commits are exactly
    `Co-authored-by: agy-worker <agy@team.local>`.
11. `commit_msg.txt` is gone from the author's worktree.

## Result

Write your marker to `.team/signoffs/agy-r3-skills-<first-12-of-sha>.md` with the
standard front matter (`reviewed_branch`, `reviewed_sha` as the full 40
characters, `reviewed_by: claude-worker`, `authored_by: agy-worker`, `timestamp`,
`tests_run`, `result`).

`result: signed` if claim 1 holds and nothing regressed. `result:
changes-requested` only if the guarantee still does not hold, or a new defect
landed. Do not withhold over the out-of-scope items above.

Commit the marker on `claude/r3-rev-skills` with the trailer exactly
`Co-authored-by: claude-worker <claude@team.local>`. Do not push.
