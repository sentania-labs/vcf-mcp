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
