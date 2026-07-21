# 004: admin UI, server-rendered Starlette and Jinja2

- **Status:** accepted; the jinja2 dependency was **approved by the principal 2026-07-21**. The escalation is closed and no term of this record changed as a result. The team had verified jinja2 is not transitive from `mcp`, so it is a genuine new dependency and required the escalation it got.
- **Date:** 2026-07-20
- **Assignment:** vcf-ops-mcp round 1, architecture forks 1-6
- **Orchestrator run:** `orchestrator-run-20260720-231633`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker

## Context

Fork 4. The admin UI is where VCF Ops targets are registered, credentials
entered, action execution enabled per target, and API keys minted. It is the
highest-impact surface in the product. files-hosting's session-auth pattern is
the lab precedent. The fork was server-rendered minimal versus SPA.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/round1-architecture` | `85cf71244b042709972e8fce4240b3b916965147` |
| codex-worker | `codex/round1-architecture` | `86b3404056be6f67337294dd47bedb477df6a84b` |
| agy-worker | `agy/round1-architecture` | `68e30bdec4329cdb65af5a278ed3388675ba6046` |

All three proposed server-rendered with Jinja2 and no SPA. They diverged on
the host framework (Starlette for claude-worker and codex-worker, FastAPI for
agy-worker), on password hashing (scrypt for codex-worker, bcrypt for
agy-worker, unspecified for claude-worker), and on how much hardening beyond
the files-hosting precedent was required.

## Critique (phase 2, adversarial)

**codex-worker on agy-worker (4):** FastAPI, Jinja2, cryptography, and bcrypt
are proposed without flagging dependency escalation, and codex named this a
constitution violation in those terms: "**new dependencies require
escalation**." A signed cookie provides no CSRF protection, session rotation,
idle expiration, recent reauthentication, or secure bootstrap delivery.

**claude-worker on agy-worker (A6):** five new dependencies with no escalation.
Separately on bcrypt: it truncates input at 72 bytes, which is a real footgun
for a bootstrap admin password fed from a generated secret. FastAPI on top of
the SDK's Starlette adds routing and validation a five-form admin UI does not
need.

**codex-worker on claude-worker (5):** supplying the admin password hash in an
environment variable recreates the process-environment exposure class
claude-worker cites elsewhere, and leaves rotation and first-login
invalidation vague. A 14-day signed boolean session is too long for a UI that
can enable actions and mint capable keys.

## Decision (phase 3, synthesis)

**Server-rendered, no SPA, no build step.** Unanimous, and the reasoning is
sound: few forms, no rich client state, and no reason to add a JavaScript
build and its auth surface to a security-critical admin plane.

**Starlette and Jinja2, in the same process**, mounted alongside the MCP app
per 002. FastAPI is rejected for the reasons in 002 and A6: it is a new
dependency added for no stated requirement, on top of a Starlette that the SDK
already provides.

**scrypt, not bcrypt**, on claude-worker's 72-byte truncation argument. The
bootstrap admin password is expected to come from a generated secret, which is
exactly the input bcrypt silently truncates.

**Bootstrap delivery fails closed.** codex-worker's design carries over
claude-worker's environment variable: accept the bootstrap admin password only
through an operator-supplied secret file, validate its ownership and mode,
hash it into the encrypted store once, then delete or invalidate the bootstrap
value. The server must refuse to start rather than come up with a default
credential.

**Hardening beyond the files-hosting precedent.** The precedent is adopted
where it is right (scrypt hashing, constant-time username comparison, session
cleared on login and logout, signed `HttpOnly` `Secure` `SameSite=Strict`
cookie, external `next` targets rejected, 401 rather than redirect for JSON
callers, every management route protected) and extended where this UI's blast
radius is larger:

- A per-session CSRF token, constant-time compared, on every state-changing
  form. A signed cookie is not CSRF protection, and agy-worker's proposal
  treated it as though it were.
- Session rotation at login.
- A short idle lifetime. The 14-day session is rejected.
- Recent reauthentication required before enabling actions on a target,
  minting an API key, or rotating keys.

**Deployment handoff remains pending.** The fleet-caddy slot facts do not
exist yet, so the exact bootstrap secret delivery mechanism is specified in
shape (mounted file, validated, imported once) but not in path. This is the
CI deploy job the assignment already allowed to slip to a later round.

## Escalated to the principal

**`jinja2` is a genuinely new dependency.** Verified: it is not transitive from
`mcp==1.28.1`. The constitution routes new dependencies to the principal.
CLAUDE.md "Pinned tooling" delegates "the admin UI stack" to a round-1 decision
record, so there is a reading in which jinja2 is covered by that delegation as
part of the stack. The orchestrator does not resolve that tension unilaterally
in favor of the team: the team's recommendation is jinja2, and Scott ratifies.

`fastapi` and `bcrypt` are also not transitive, and both are rejected above, so
no escalation is needed for either.

## Division of labor

| Piece | Assigned to | Why this harness |
| --- | --- | --- |
| Admin routes, forms, templates, target CRUD, key management, audit views | codex-worker | It specified the hardened session model in the most detail and found the bootstrap exposure defect in claude-worker's proposal |
| CSRF, session rotation, idle expiry, recent-reauth gates | codex-worker | Same surface; splitting session hardening from the routes that depend on it would split one invariant |
| Bootstrap secret-file import, ownership and mode validation, fail-closed startup | claude-worker | Adjacent to the keyring startup checks it owns in 003, and the same fail-closed discipline applies |

Note the deliberate asymmetry: agy-worker receives no slice of this fork. Its
fork 4 proposal lost on every contested point (FastAPI, bcrypt, CSRF, session
hardening, dependency escalation) and its harness has no stated advantage on a
server-rendered auth plane. Per the orchestrator brief, that is a normal
outcome and not a slight. agy-worker holds slices in 001 and 006.

## Dissent

None standing. agy-worker did not contest the FastAPI, bcrypt, or session
findings in its critique or ballots.

**Constitution-violation claim, resolved.** codex-worker's claim that
agy-worker's proposal violated the new-dependency escalation rule was upheld.
The escalation for jinja2 above is the remedy; fastapi and bcrypt are rejected
outright. agy-worker did not contest it, so no principal escalation of the
claim itself is required.

## Protected paths touched

src/vcf_ops_mcp/

## Sign-offs

    Signed-off-by: claude-worker <claude@team.local> 2026-07-20T23:38:12Z
    Signed-off-by: codex-worker <codex@team.local> 2026-07-20T23:33:21Z
    Signed-off-by: agy-worker <agy@team.local> 2026-07-20T23:34:00Z

Transcribed by the orchestrator from each worker's own signature artifact,
because the records live on a branch the workers do not write to. The
artifacts are authoritative and independently checkable:

| Signer | Signature artifact | Commit |
| --- | --- | --- |
| claude-worker | `.team/signoffs/claude-worker-round1-records.md` | `4cde29b` |
| codex-worker | `.team/signoffs/codex-worker-round1-records.md` | `dd9cf51` |
| agy-worker | `.team/signoffs/agy-worker-round1-records.md` | `9576887` |

Each signer confirmed in its artifact that its own dissent, where it has one,
is quoted accurately and was not softened or truncated.
