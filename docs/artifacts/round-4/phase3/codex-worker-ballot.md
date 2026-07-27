---
source-ref: b71f8b5
source-commit: b71f8b5626135f717217f688323e616b7f6785fe
source-blob: 7385140917ea46cee3bf805fb1008c95c13bdf2c
source-path: docs/proposals/4/codex-worker-ballot.md
worker: codex-worker
round: round-4
phase: phase3
captured: 2026-07-27
---

# Round 4 ballot, codex-worker

## Question A

**Vote: for.** Deploying the existing immutable `github.sha` tag removes the
untested output plumbing I opposed, and the split gives the permissions and
package publication path a real round-branch exercise before merge. Round-branch
publication should be a numbered decision Scott can veto; if vetoed, retain the
single main-only job and accept that the first package push remains a post-merge
test. I argued against the earlier split mechanism.

## Question B

**Vote: against, regardless of Question A.** A standalone rename commit answers
the attribution objection, but it does not preserve Actions run continuity or
reduce the operational variables during the first deployment repair. The stale
name should be corrected in a later housekeeping change after deployment is
proven. I previously argued to defer the rename.
