# 019: Complete governance controls and rename the live project

- **Status:** accepted by principal directive
- **Date:** 2026-08-25
- **Assignment:** Deliver authorization modes, backend-pack trust, response
  redaction, authentication lockout, upstream traffic control, the inherited
  store contract, and the live project rename in one pull request.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** principal directives, 2026-08-24 and 2026-08-25: deliver the
  settled VCF MCP specification as one complete change, then include the live
  project and Python-package rename while preserving historical records.

## Context

The multi-backend read surface was runnable, but it still had one authorization
posture, unsigned startup packs, no cross-request authentication lockout, no
bounded 429 response, and an incomplete inherited credential-store contract.
The repository also retained the predecessor project name throughout live code,
packaging, deployment configuration, and instructions.

This is a directive-authority record. The principal already settled the
authorization, trust, redaction, traffic-control, persistence, and rename
requirements. No worker proposal or critique round was needed or authorized.

## Decision

The runtime stores one instance-wide authorization mode. Local keys use
explicit endpoint and tool scopes and default to no tool scope. Gateway keys
hold every implemented tool scope, are limited to one active key per endpoint
registration, and remain endpoint-specific. Every mode change revokes every
active key in the same transaction and records the revoked count. Every tool
audit row records the mode and key owner. The interface states that gateway
mode still needs a network or mutual-TLS reachability boundary and cannot claim
downstream agent identity.

Backend packs remain data only and startup frozen. Operator packs enter through
one trust manager that invokes a digest-pinned cosign binary with an argument
array. Verification pins the exact main-branch release workflow identity and
GitHub Actions issuer, uses the bundle shipped with the pack, and supplies the
baked Sigstore trust root. Manual upload and the fixed feed both stage for the
next restart. Prior versions remain available for one-action rollback. Unsigned
installation is off by default, persists a visible warning when enabled, and is
refused whenever any target permits actions.

Every declared tool now carries its own response-field allowlist. A pack cannot
fall back to a backend-wide shared allowlist, which prevents a sensitive tool
from inheriting a field that another tool legitimately returns. Per-target
authentication failures persist across requests and lock after three
consecutive failures until an operator clears the state in the interface.
Every backend client admits bounded concurrent work and retries 429 responses
with a bounded exponential delay, logging the first activation.

The credential store uses length-prefixed additional authenticated data for new
envelopes while retaining safe read compatibility for existing envelopes.
Rotation adds a durable progress row, processes bounded batches, resumes after a
crash, and retires unused keys only after completion. Startup verifies every
target envelope, quarantines an individual bad row, and refuses startup when
all configured targets fail. Database backup writes only a SQLite artifact and
refuses the keyring volume. The restore gate proves that database artifact with
a separately held keyring.

The live Python package is `vcf_mcp`, matching the `vcf-mcp` repository,
container, deployment, documentation, skill metadata, and instruction names.
Files under `docs/decisions`, `docs/artifacts`, and `docs/history` that predate
this change remain byte-identical. They are evidence of the project name and
paths that existed when those records were written.

## Operational consequence

Mode changes have an intentionally broad and recoverable blast radius: all old
keys stop on the next request, and operators mint replacements for the selected
mode. Authentication lockout prevents a bad target configuration from driving a
directory account into an appliance-side lockout. Pack installation never
changes the running tool registry, so activation and rollback each require a
container restart. Credential rotation is online and resumable, but old key
material remains until every usable target has been re-encrypted.

Fixture and browser-level tests prove the local enforcement and recovery paths.
Appliance authentication behavior, real 429 timing, gateway network isolation,
offline verification of a real release bundle, action posture on DEVEL, and the
separate-volume restore remain operator-run lab evidence and are not claimed by
this record.

## Protected paths touched

`docs/SPEC.md`

`CLAUDE.md`

`AGENTS.md`

`src/vcf_mcp/`

`.github/protected-paths.txt`

## Sign-offs

None. This implementation directly executes the principal's settled product,
safety, persistence, and rename requirements recorded above.
