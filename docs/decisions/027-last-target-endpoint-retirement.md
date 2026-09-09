# 027: Last-target endpoint retirement

- **Status:** accepted by Captain directive
- **Date:** 2026-09-09
- **Assignment:** Implement issue 14, deleting a target and revoking every API
  key scoped to it as one confirmed action.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** Captain directive, 2026-09-09: keep the already mounted endpoint
  until the next explicit restart, make the deleted target immediately unusable,
  mark restart required, and explain that the endpoint disappears after restart.

## Context

Product endpoints and their tool surfaces are derived from registered targets at
process startup, then frozen for the process lifetime. Removing the last target
for a product therefore requires an explicit choice between changing the running
route table or retaining an endpoint whose final target is gone.

Target deletion also removes encrypted credentials and revokes every active API
key scoped to that target. Operators must see the full key blast radius before
committing an irreversible change.

This is a directive-authority record because the Captain selected the endpoint
retirement behavior directly after accepting the issue assessment. No worker
proposal round ran.

## Decision

Deleting a target and revoking all active API keys scoped to it occurs in one
SQLite transaction. The transaction records one event for each revoked key and
one target-deletion event containing the revocation count. Existing historical
tool-call and configuration audit records remain untouched.

The console first shows the target and each affected key by name, together with
the backends that key covers. Its confirmation carries a digest of the exact
displayed target and key state. A changed target or key set invalidates the
confirmation and requires a fresh preview. The committing request uses the same
authenticated, recently reauthenticated, CSRF-protected governance boundary as
other sensitive console actions.

After the transaction commits, new calls have no authority because scoped keys
are revoked and the target no longer resolves. The console cancels and awaits
already-running calls through the target client invalidator before reporting
success. The pool retains clients already draining after an edit until their
requests and transport close have settled, so deletion also cancels those older
generations. Every pool invocation is registered before any wait, including
authentication, client acquisition, and shared concurrency slots. Cancellation
awaits these registered calls and rejects late calls using a cancelled target
generation. Key backend coverage comes from allowed targets; endpoint scope is
displayed separately.

When the deleted target was the last target for its product, the already mounted
endpoint remains in the current process until the next explicit restart. The
transaction marks restart required. The console states that the deleted target
is already unusable, the endpoint stays mounted until restart, and the endpoint
disappears after restart. This preserves the startup-frozen routing model and
avoids changing route ownership while requests may still be connected.

## Dissent

None. The implementation follows a direct Captain decision.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this decision, so it has no
worker sign-off lines. The `Authority` field above stands in their place.
