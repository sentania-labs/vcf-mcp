# 021: enforce private-file isolation outside the service group

- **Status:** accepted by principal directive
- **Date:** 2026-08-25
- **Assignment:** Repair startup with legacy and Kubernetes `fsGroup` private
  files while preserving service-user ownership and preventing access by users
  outside the service group.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** principal directive, 2026-08-25: implement issue 10 with
  self-correction to `0600`, accept group-only access when correction is not
  possible, retain the ownership requirement, and expose refusals in startup
  logs and `/healthz`.

## Context

Version 0.3.0 required every private file to have mode exactly `0600`. That
refused `0660` files written by an earlier application version and files on a
Kubernetes persistent volume where `securityContext.fsGroup` applies group
ownership and group-write access. The process then stayed reachable but
unready, while the concrete permission failure was buried below a generic 503.

The issue suggested testing `mode & 0o077`, but that mask includes group bits
and would still reject `0660`. The directive corrected the governing property
to the `other` permission bits represented by `0o007`.

This is a directive-authority record. The principal specified the permission
boundary and recovery order directly, so no proposal round was authorized or
needed.

## Decision

A private file must remain a regular file owned by the effective service uid.
Ownership by any other uid is refused before any repair is attempted.

When an owned file has group or other permissions, startup first attempts to
change it to `0600`. Successful correction is logged with the path and prior
mode. If correction fails, any `other` permission causes refusal with the path,
mode, cause, and remediation. Group permissions alone are accepted and logged
only when the file's group is the process effective group or one of its
supplementary groups. This verifies that group access represents the service's
Kubernetes `fsGroup` boundary rather than access outside that boundary. An
unrelated file group is refused with the file gid, the service gids, and
remediation.

New session secrets, audit digest keys, and credential keyrings continue to be
written atomically with mode `0600`. Startup failures remain degraded and
reachable, but their complete cause chain is recorded in startup logs and the
`/healthz` response.

This permits removal of the initContainer permission workaround tracked in
`sentania-labs/lab-deployment#23` after the fixed appliance is deployed.

This record supersedes only the exact-`0600` startup refusal stated for the
admin bootstrap file in record 014. Its creation mode remains `0600`, while an
existing service-owned file follows the correction and service-group fallback
defined here.

## Dissent

None. The implementation follows a direct principal instruction.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this change, so it
carries no worker sign-off lines. The `Authority` field above stands in their
place.
