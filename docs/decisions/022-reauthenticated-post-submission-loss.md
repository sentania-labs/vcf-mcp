# 022: Prevent silent loss of reauthenticated submissions

- **Status:** accepted by Firstmate directive
- **Date:** 2026-08-26
- **Assignment:** Prevent expired recent authentication from silently discarding
  sensitive admin-console POST submissions.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** Firstmate 2026-08-26 decision on the single external review
  round for PR 18.

## Context

An expired recent-authentication window could redirect a valid sensitive POST
to password confirmation without telling the operator that the submitted
change was discarded. A reauthenticated submission must never be silently
discarded.

This is a directive-authority record because Firstmate selected the remedy
directly during the single external review round. No worker proposal round ran.

## Decision

Every sensitive admin POST validates CSRF before checking recent
authentication. When authentication has expired, the server retains no
submitted field or password. It stores only a session-scoped, expiring notice
that says the change was not saved and must be submitted again after password
confirmation.

Reauthentication returns only to the local `/admin` path and never replays the
POST as a GET. The operator must re-enter and resubmit the change after
authentication.

## Dissent

None. The implementation follows a direct Firstmate decision.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this decision, so it has
no worker sign-off lines. The `Authority` field above stands in their place.
