---
source-ref: 88bc5f9
source-commit: 88bc5f969631562a2d212f8baf18e78b938ce767
source-blob: 071972f9303bcfc6f0fa86dbbd1019df0c96c9f0
source-path: docs/proposals/4/claude-worker-ballot.md
worker: claude-worker
round: round-4
phase: phase3
captured: 2026-07-27
---

# Round 4 ballot, claude-worker

Seat: claude-worker. Branch: `claude/r4-deploy-permissions`.

## Question A: split `deploy` into `build` and `deploy`

**Vote: for.** Interest declared: I proposed the split, and I am the one who
dropped the `needs.build.outputs.digest` mechanism that both peers attacked, so
read this vote as a party's.

The revised form has no plumbing to get wrong: the build job pushes
`:${{ github.sha }}` exactly as line 67 already does, the deploy job keeps its
`if: github.ref == 'refs/heads/main'`, and `github.sha` is a context expression
available in both without an output boundary. That turns the permissions fix
from an assertion into an observed result on the round branch, and it surfaces
package creation, visibility, and repo linkage before the merge rather than
after. The against-case's real content is not testability, it is that we would
publish an organization image built from code that has not passed the round PR's
external review.

**That cost is Scott's to accept, so make it a numbered decision he can veto.**
It widens what the repo publishes, which is the kind of thing the constitution
sends up rather than settling in-team. Stated fallback if he vetoes: keep one
`deploy` job, ship the `permissions:` block and the preflight unchanged, and
accept that the first real exercise is on `main`, which is where this workflow
stands today anyway. The fallback is the status quo plus the fix, so a veto
costs the round nothing it currently has.

## Question B: rename `ai-log-depot.yml` to `vcf-ops-mcp.yml`

**Vote: for**, in the standalone-commit form: a `git mv` plus the one-line
`name:` change, committed before the substantive commit. Not a party to this
one.

The standalone-commit ordering answers the git-history half of the attribution
objection completely, `git show` on the substantive commit is three readable
lines. It does not answer the Actions-history half, because the UI groups runs
by workflow, and I do not think it needs to: the deploy job has never succeeded
here, so there is no green predecessor run an operator would be comparing
against, and the old runs stay reachable under the old name regardless. Against
that, the window argument is the strongest thing on this ballot, the day
somebody adds a required status check the rename stops being free.

**Not conditional on A.** If A fails, the scarcity argument gets stronger and I
still vote for: one main-only attempt is a reason to keep the substantive commit
small and separable, which is exactly what the standalone-rename ordering buys.

Co-authored-by: Claude <claude@team.local>
