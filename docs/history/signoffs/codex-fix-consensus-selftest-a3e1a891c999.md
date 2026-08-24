---
reviewed_branch: codex/fix-consensus-selftest
reviewed_sha: a3e1a891c9997474542d663dd2d8f86273057b3f
reviewed_by: claude-worker
authored_by: codex-worker
reviewed_at: 2026-07-20T23:37:27Z
tests_run: python3 tools/consensus-check.py --self-test
result: signed-off
---

I reviewed `ca66ccf..a3e1a89` read-only. I did not enter or modify the codex
worktree; I read the branch via `git diff`/`git show` from my own worktree and
ran the self-test from a throwaway detached worktree checked out at `a3e1a89`,
which I removed afterward.

The diff is one line in `tools/consensus-check.py:572`, replacing the
self-test's required-entry assertion `src/photoflow/` with
`src/vcf_ops_mcp/`. Nothing outside `tools/` is touched, so no protected path
is in the diff and no decision record is required. `git merge-base` confirms
the branch is a single commit off `round/1-architecture` at `ca66ccf` with no
drift.

Checks I actually ran:

1. **Replacement matches the config exactly.** `.github/protected-paths.txt`
   lists `src/vcf_ops_mcp/` with the trailing slash under the safety-critical
   server core section. `load_protected_paths` compares entries verbatim, and
   the new literal is byte-identical to the config line, so the assertion is a
   real check rather than one that happens to pass.
2. **The fix is load-bearing.** At base `ca66ccf` the self-test fails with
   `FAIL protected-paths config is missing required entry: src/photoflow/`
   (exit 1). At `a3e1a89` it prints `All consensus-gate self-tests passed.`
   (exit 0). The bug was live, not hypothetical.
3. **No other leftovers of the same class in `tools/`.** I grepped `tools/`
   for `photoflow`, other `src/<name>/` path literals, `github.com/<owner>/
   <repo>` and `ghcr.io/<owner>/<image>` references, and `sentania-labs/*`
   repo names. The only hits are `src/core/`, `config/app.toml` and
   `ARCHITECTURE.md` inside `self_test()`, and those are deliberately
   synthetic: they are built as an in-memory `protected` list and exercised
   against a `tempfile.TemporaryDirectory()` root, never against this repo's
   real config. They are generic matcher fixtures, not stale template values,
   so they are correct as they stand. Line 572 was the only place the
   self-test asserted against the real on-disk config, which is exactly why it
   was the only place the template name survived.
   `tools/generate_agents_md.sh` reads clean.
4. **Style.** No em-dashes in the diff or in the commit message. The commit
   carries `Co-authored-by: Codex <codex@team.local>`.

One non-blocking observation for the author, not a condition of this
sign-off: the comment at `tools/consensus-check.py:516` still cites
`001-town-motion.md` as the record that predates the workers field. No such
record exists here (this repo's 001 is `001-action-tool-surface.md`), so that
line is a template leftover too. It is prose in a comment with no effect on
behavior, and the loop below it globs `[0-9][0-9][0-9]-*.md` and validates
whatever records are actually on disk, so nothing is mis-checked. Worth
sweeping in a later pass; it does not belong in this one-line fix.

Signed off.
