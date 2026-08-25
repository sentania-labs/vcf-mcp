# 016: Multi-backend endpoint prototype

- **Status:** accepted by principal directive
- **Date:** 2026-08-25
- **Assignment:** Build a workable prototype of the captain's VCF MCP spec,
  including the added target editing and TLS trust requirements.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** principal directive, 2026-08-25: deliver a prototype where
  Operations and vCenter are registered in the UI and called through their own
  typed MCP endpoints, with editable targets and per-backend uploaded CA trust.

## Context

Version 0.1.0 shipped one VCF Operations surface at `/mcp`. It did not establish
the endpoint-per-backend architecture, a second auth scheme, a data-only backend
content model, or the management endpoint. Registration also left an operator
unable to correct a target or establish CA trust without leaving certificate
verification disabled.

This is a directive-authority record. The captain specified the product shape,
the prototype boundary, and the cancellation behavior directly. There was no
worker proposal round to sign.

## Decision

The server enumerates registered backend kinds at startup and freezes a separate
FastMCP registry for each one. Operations is mounted at `/ops/mcp`, vCenter at
`/vcenter/mcp`, and read-only management at `/vcf/mcp`. A missing registration
means the corresponding product endpoint does not exist.

Built-in JSON packs carry static tool definitions, paths, methods, permitted
query and body keys, projections, caps, declared auth schemes, and product
identity. The packs select only authentication schemes and handlers already
implemented by the container. Their tool registrations still pass through the
existing mandatory dispatcher. Audit attempts and terminal rows record the
endpoint and the defining pack's ID, digest, and version.

The prototype packs are unsigned. The runtime repository structurally refuses
an actions-enabled posture while that is true. Signing, pack installation,
rollback, gateway mode, auth circuit breaking, rate limiting, redaction, and
token-budget enforcement remain outside this record.

Target registration and editing share one runtime repository and one encrypted
AES-256-GCM envelope mechanism. The editable fields are display name, FQDN,
credentials, auth source, posture, root CA, and TLS verification. Root CA
bundles are validated as PEM and encrypted under a field-specific purpose.

TLS verification defaults off and is labelled as unsafe in the admin UI. Each
target constructs its own HTTP client verifier from either system roots or its
uploaded CA bundle. No process-wide TLS switch exists. A false-to-true TLS edit
cancels in-flight calls on that target. Replacing or removing the target's CA
also cancels, so no work is allowed to finish under superseded trust.

Fingerprint pinning is not part of this implementation.

## Operational consequence

After an operator registers the first target for each product and restarts the
container, clients can connect independently to Operations and vCenter. Target
and key changes remain UI-driven. Existing encrypted credentials migrate in
place as Operations targets, and existing keys retain Operations plus management
endpoint access.

Real appliance compatibility and reverse-proxy behavior require Scott's lab and
are not claimed by this record. Fixture proof is recorded in
`docs/PROTOTYPE.md`.

## Protected paths touched

`src/vcf_ops_mcp/`

## Sign-offs

None. This is a principal-directed implementation whose authority is recorded
above, and it names no team worker as dispatched.
