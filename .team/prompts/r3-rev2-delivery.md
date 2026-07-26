# Re-review: delivery slice, `agy/r3-delivery` at `5bd75c6`

You are codex-worker. You are the peer reviewer. You did not author this slice;
agy-worker did. Do not fix anything you find. Your product is one sign-off
marker.

## What you are reviewing

Branch `agy/r3-delivery`, now at
`5bd75c628e594e502f3f3d57566cba83f5968cc6`.

The author's worktree is `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-agy`.
You may read it and run tests there, but **treat it as read-only**: change
nothing in it, and confirm `git status --porcelain --untracked-files=no` is empty
there when you finish. Commit your marker in your own worktree, on your own
branch `codex/r3-rev-delivery`.

## Scope: two items, and only two

You re-reviewed this slice at `11b0227` and requested changes on exactly two
Tier 1 items. Your marker is `.team/signoffs/agy-r3-delivery-11b0227e9dd2.md`.
Everything else you assessed there stands: Tier 1 items 2, 3 and 5 are CLOSED,
the volume declarations are CLOSED, and the six Tier 2 remainders are the next
increment's worklist and are **deliberately out of scope for this re-review**.
Do not reopen them, and do not block on them.

The two items:

1. **Restore the eleven baseline files** the cleanup deleted that predate this
   slice, while keeping the 45 slice-local artifacts removed.
2. **Six trailing-whitespace errors** from `git diff --check 19efb0c..11b0227`.

## Named claims to confirm or deny

The orchestrator ran these before dispatching you and got the results shown.
**Do not take them on report. Re-run them.** Withholding on any claim is valid,
and saying "I could not check this" is a better answer than a confirmation you
did not earn.

1. `git diff --diff-filter=D --name-only 33bca5d 5bd75c6` lists **zero** files.
   None of the eleven baseline files is still deleted.
2. All eleven named files exist in the tree at `5bd75c6` with their `33bca5d`
   content, byte for byte. Check the content, not just the presence.
3. The 45 slice-local artifacts were **not** re-added as a side effect of the
   restore. The full added-file set versus `33bca5d` is twelve files:
   `.github/workflows/ai-log-depot.yml`, two `.team/markers/` files, `Dockerfile`,
   `pyproject.toml`, four `src/vcf_ops_mcp/` files, and three `tests/` files. No
   `.patch`, no `diff.txt`, no `log.txt`, no `scratch/`.
4. `git diff --check 19efb0c 5bd75c6` produces no output and exits 0.
5. The two source whitespace fixes (`src/vcf_ops_mcp/app.py:60`,
   `tests/test_admin.py:23`) made the blank lines empty rather than deleting the
   lines and shifting code.
6. The four `.team/markers/` whitespace fixes stripped only the trailing space
   after `model:` and `injected_secret_keys:`, and did not otherwise alter or
   delete a marker's recorded content.
7. The suite passes: 20 passed, using
   `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --no-project --with 'mcp>=1.2.0' --with jinja2 --with python-multipart --with itsdangerous pytest -p no:cacheprovider`.
   Note that a bare `python3 -m pytest` fails collection with
   `ModuleNotFoundError: No module named 'mcp'` in an ambient env without the
   deps; that is an environment artifact, not a slice defect. Say which you
   observed.
8. Nothing in the two Tier 1 fixes regressed items 2, 3 or 5. Specifically: the
   workflow still contains none of `sentania.net`, `vcf-lab`, `docker.int`;
   `post_login` still returns 501 with no literal `"admin"`; `create_app` still
   raises `RuntimeError` without `SESSION_SECRET`; both jobs are still
   `runs-on: [self-hosted]`.
9. The commit trailer on `5bd75c6` is exactly
   `Co-authored-by: agy-worker <agy@team.local>`.
10. `pyproject.toml` at the slice root makes a bare `pytest` collect from the
    repository root without a `PYTHONPATH` override. This one is new and matters
    beyond the slice: the round branch had no `pyproject.toml`, `conftest.py` or
    `pytest.ini`, and CI runs the literal command. Report what you actually
    observe, including if the answer is that `PYTHONPATH=src` is still required.

## Result

Write your marker to `.team/signoffs/agy-r3-delivery-5bd75c628e59.md` with the
standard front matter (`reviewed_branch`, `reviewed_sha` as the full 40
characters, `reviewed_by: codex-worker`, `authored_by: agy-worker`, `timestamp`,
`tests_run`, `result`).

`result: signed` if both Tier 1 items are genuinely closed and nothing regressed.
`result: changes-requested` only if one of the two named items is still open, or
if a fix introduced a new defect. Do not withhold sign-off over a Tier 2
remainder; those are scoped out and the orchestrator has recorded them.

Commit the marker on `codex/r3-rev-delivery` with the trailer exactly
`Co-authored-by: codex-worker <codex@team.local>`. Do not push.
