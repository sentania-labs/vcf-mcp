# 014: Firstmate MVP completion and generated session secret

- **Status:** accepted by direct implementation authority
- **Date:** 2026-07-30
- **Assignment:** Firstmate `vcf-ops-mcp-mvp`
- **Orchestrator run:** none
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None
- **Authority:** the Firstmate launch brief explicitly authorizes implementation
  of a coherent container and admin-UI MVP, requires issues #5 and #7 to be
  resolved, and requires startup without a hand-populated `SESSION_SECRET`.

## Context

Main already contained the durable SQLite audit repository selected by record
013 and wired it through `create_production_app`. That fixed the
audit-injection half of issue #5, but record 013's session-secret half required
lab-admin to create a slot `.env` by hand. The public service therefore still
could not deploy, and the real uvicorn factory path still exited before binding
when that file was absent.

The implemented Phase 1 components were also disconnected. The read-plane
adapters, mandatory dispatcher, API-key contracts, admin authentication
helpers, and skills catalog all had tests, but the mounted FastMCP instance had
no registered tools or bearer verifier. Admin login and target registration
returned 501. A product with individually tested components but no core journey
was not a usable MVP.

Issue #7 independently showed that `cache: pip` in `actions/setup-python`
converted an unwritable optional cache on one self-hosted runner into a hard
job failure before installation or tests.

## Decision

### Session secret

The normal production path generates a random session signing secret on first
start and persists it as `/keys/session_secret` with mode 0600. Later process
and container starts reuse the same value. The write is atomic and committed to
the mounted directory. `SESSION_SECRET` remains an explicit operator override
for direct process operation, but it is no longer required by compose or CI.

If the key volume cannot safely persist the secret, the process starts only to
report a meaningful 503. It uses a transient in-memory value for the diagnostic
admin middleware, marks `session_secret_persistent` false, and is not ready for
traffic. It never logs the secret.

This decision supersedes only record 013's "Half A: SESSION_SECRET" slot-env
choice. Record 013's append-only SQLite ledger, reconciliation, composition
root, and health-gate decisions remain unchanged.

### Runtime configuration and admin UI

The MVP completes the already accepted designs from records 003, 004, and 009:

- One SQLite runtime database on `/data` stores the scrypt admin hash, public
  target metadata, AES-256-GCM credential envelopes, and SHA-256 API-key
  digests.
- A versioned credential keyring on the separate `/keys` volume binds each
  ciphertext with associated data containing schema version, target ID, field
  purpose, and key ID. A missing keyring is generated only when no encrypted
  target exists. It is never regenerated over ciphertext.
- Admin bootstrap keeps record 004's operator-supplied secret-file design. The
  file is required only to initialize admin login, not to start or become
  healthy. It must be owned by the service user at mode 0600, is hashed once,
  and is removed after consumption.
- The admin UI supports login, recent reauthentication, CSRF protection,
  read-only target registration, read-scoped API-key mint and revoke, and audit
  viewing. No action control is present.

No new runtime dependency is introduced. SQLite is in the standard library,
and AESGCM, Starlette, Jinja2, and the MCP SDK were already approved runtime
dependencies.

### MCP composition

The private FastMCP instance is built only in the production composition root.
It receives a bearer verifier backed by the runtime API-key repository. Every
registered VCF read adapter is wrapped by the mandatory dispatcher, and the
same dispatcher covers target and skills tools. The request identity comes
from the verifier on every request and is attached to the current FastMCP
request context before dispatch.

The mounted path is `/mcp/`, stateless Streamable HTTP. DNS rebinding
protection permits only the configured public host plus loopback development
hosts. The parent app adopts the child MCP lifespan.

All minted keys receive only capabilities claimed by adapters registered in
this build, intersected again inside the dispatcher. Keys require at least one
allowed target. Targets are always created read-only. The production FQDN is
derived server-side and remains hard-blocked. `MUTATING` remains empty.

Actions, action-capable keys, report runs, plan/apply, and target posture
changes remain outside this MVP and behind the Phase 2 human gate.

### CI cache

The repository removes `cache: pip` from `actions/setup-python`. Dependency
installation and tests remain mandatory. An unusable runner-local cache now
means a slower uncached installation, while actual install or test failures
still fail the job. A static regression test checks that the cache option does
not return.

## Operational consequence

A fresh container with writable `/data`, `/keys`, and `/audit` volumes reaches
HTTP 200 from `/healthz` without an operator-created session secret. The first
admin sign-in has one documented password-file step. Runtime state and audit
records survive process and container restart.

## Protected paths touched

`src/vcf_ops_mcp/`

## Sign-offs

None. This is a direct Firstmate dispatch whose authority is recorded above,
and it names no team worker as dispatched.
