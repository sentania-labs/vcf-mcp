# Codex worker, round 1 peer critique

I read the Claude and Agy proposals from their named commits after phase 1
closed. I did not enter or modify either peer worktree.

## Claude worker

### Steelman

Claude's strongest case is that live DEVEL measurements, package inspection,
and the repository's operating lessons all point to one compact design: fixed
tools over projected public API adapters, the official SDK's bundled FastMCP
layer, a versioned AES-GCM store, and a server-rendered Starlette UI. Its
missing premise is that stable client schemas and server-side policy boundaries
matter more than making each appliance capability look native to the model.
That premise is correct. Claude is better than my proposal on measured payload
projection and on identifying that action catalog entries lack parameter
metadata, and I would adopt both findings.

### Attack

1. **Fork 1, action authorization.** Claude proposes a checked-in global action
allowlist and says expanding it is protected-path work, but
`.github/protected-paths.txt` is the authority and the proposal does not show
that this new file would be covered. More importantly, an actions-capable key
gets every globally allowed action. That makes one compromised automation key
capable of power, reconfiguration, snapshot deletion, and DRS changes across
its target allowlist. Use per-key action-class or action-ID subsets, intersected
with a global server policy. Keep the default empty. This policy choice and the
allowlist seed widen action blast radius, so they require principal escalation.

2. **Fork 1, plan freshness and audit ordering.** Claude explicitly leaves a
TOCTOU hole between population and apply. A body hash proves only that the
client did not alter the plan. It does not prove the resource, populated
defaults, catalog, target posture, or key authorization stayed valid. Persist
one-use plans and, at apply, atomically claim the plan, recheck all policy, and
repopulate or validate against VCF Ops before mutation. A timeout must end in
`outcome_unknown`, never an automatic retry. Also, writing an audit record
before POST is insufficient unless completion or unknown outcome is durably
recorded afterward. Every accepted, denied, failed, and completed tool call
needs a terminal audit status.

3. **Fork 2, audit boundary.** A Starlette request middleware sees MCP HTTP
requests, not necessarily individual tool invocations or their normalized
arguments and result status. Streamable HTTP can carry protocol traffic whose
request count does not equal tool-call count. Therefore middleware cannot by
itself satisfy the invariant that every tool call is audited. Route every tool
handler through one mandatory audited dispatcher and test registration fails
or execution is impossible without that wrapper. Keep HTTP middleware only for
request identity and correlation.

4. **Fork 3, API-key cache and dependency ruling.** A 60-second positive key
cache contradicts the claim that revocation is immediate and creates a real
post-revocation action window. Cache only immutable public lookup data, or
invalidate synchronously on revoke and recheck key status during apply.
Claude also says the cryptography choice needs no escalation because it is a
transitive dependency. That is wrong under this repository's rules: the pinned
tooling section explicitly makes credential-store encryption a round-1
architecture decision before code depends on it. Treat AES-GCM, keyring
layout, recovery, and rotation as a recorded principal-approved decision.

5. **Fork 4, bootstrap secret handling.** Supplying the admin password hash in
an environment variable recreates the interpolation and process-environment
exposure class Claude cites elsewhere. It also leaves rotation and first-login
invalidation vague. Accept a mounted secret file, validate its ownership and
mode, import it once into durable storage, and require replacement at first
login. A 14-day signed boolean session is too long for a UI that can enable
actions and mint capable keys. Use a short idle lifetime, session rotation on
login, CSRF protection, and recent reauthentication for high-impact changes.

6. **Fork 5, mutable version identity.** Git history plus one mutable
`skills/<slug>/SKILL.md` does not give clients a stable address for the exact
content they used. The frontmatter semver can be overwritten while the same
`skill://<slug>` URI returns different bytes. Store immutable
`skills/<slug>/<version>/SKILL.md`, publish a digest, and make `current` an
explicit alias. The build-generated committed index also has two sources of
truth and predictable drift. Generate it in CI or validate exact regeneration,
but never trust a stale committed index at runtime.

7. **Fork 6, capability staleness.** Registration-time probes plus a manual
button do not detect an appliance upgrade until some later call happens to
observe a release name, and most domain calls will not return one. Ten targets
make manual reprobe operational debt. Probe cheaply on a bounded TTL and fail
closed for safety-relevant capabilities. Claude is right that no live Swagger
exists and that 9.0 public API contracts should be the baseline. I was less
specific about this split. Captured fixtures should be sanitized synthetic
contracts, not committed raw recon, and CI must remain free of live credentials.

## Agy worker

### Steelman

Agy's strongest version is a deliberately small fixed surface: generic action
tools preserve plan then apply, the official SDK sits inside one ASGI service,
credentials are encrypted in SQLite, and skills remain reviewed files. If the
unstated premise is that implementation simplicity is the primary Phase 1
risk, this is a coherent starting skeleton. The fixed action pipeline is the
right direction and is better than generated per-action tools.

### Attack

1. **Fork 1, guessed catalog and incomplete safety model.** Agy calls the
catalog "hundreds" without measuring it. DEVEL returned 142 definitions, all
`UPDATE`, and the list contains no parameter schemas. The missing metadata,
not the guessed count, is the decisive reason generated action tools fail.
Measure and record those facts. More seriously, `apply_action(plan_id)` names
no binding to key identity, target posture, prod identity, catalog fingerprint,
expiry, one-use consumption, or server-derived payload. A local cache alone is
replayable and stale. Persist an opaque one-use plan and recheck every
authorization and safety predicate at apply.

2. **Fork 2, stale transport claim.** `mcp.server.sse` is the old SSE path, not
the required Streamable HTTP transport. The official SDK's bundled FastMCP
already exposes `streamable_http_app()` as Starlette and accepts a token
verifier, so the claim that FastMCP hides the ASGI app is factually wrong.
FastAPI adds a dependency and abstraction without a stated requirement. Use
the official `mcp` package's Streamable HTTP application mounted in Starlette,
then prove lifespan, authentication, reconnect, resources, and prompts with a
client smoke test.

3. **Fork 3, ambiguous cryptography and missing hard block.** "Fernet or raw
AESGCM" is not a design choice. They have different primitives, envelopes,
AAD support, and rotation consequences. Specify versioned AES-256-GCM records,
fresh nonces, row-bound AAD, a multi-key rotation state machine, refusal to
regenerate a missing key over existing ciphertext, and backup/restore tests.
The key model also omits target allowlists and the unconditional prod action
block. As written, this proposal violates the constitution: **the prod
appliance is hard-blocked from actions** and **read-only is the default posture,
per target**. Enforce both independently of client scope. The new cryptography
selection also requires principal escalation.

4. **Fork 4, new dependencies and web security.** FastAPI, Jinja2,
cryptography, and bcrypt are proposed without flagging dependency escalation.
This proposal violates the constitution: **new dependencies require
escalation**. Bcrypt is also an unnecessary extra if an approved existing
primitive provides scrypt. A signed cookie does not provide CSRF protection,
session rotation, idle expiration, recent reauthentication, or secure bootstrap
delivery. Use the SDK's Starlette stack, a secret-file bootstrap that fails
closed, short hardened sessions, CSRF tokens, and reauthentication before
enabling actions or minting capable keys.

5. **Fork 5, unsafe discovery and no stable identity.** Discovering arbitrary
Markdown on boot gives no schema validation, safe path boundary, size limit,
provenance, digest, immutable version, or guarantee that resources, prompts,
and tools render the same content. At 30 skills, returning an unbounded list
also wastes context. Use a validated manifest and immutable versions, expose
metadata-only filtered listings, restrict reads to indexed paths, and ship the
content inside the reviewed image.

6. **Fork 6, optional-everything parsing.** Setting undocumented or absent
fields to `Optional` and ignoring extras prevents crashes but can silently turn
missing safety data into permissive behavior. Require fields used for identity,
pagination, authorization, action targeting, and task outcome; tolerate extras
only on descriptive payloads. Agy did no stated live recon, so this fork is an
estimate rather than evidence. DEVEL measurements already show no live OpenAPI,
HTML error bodies on some failures, and product version distinct from API
major/minor. Use public 9.0 contracts plus sanitized fixtures, bounded
capability probes, guarded error decoding, explicit pagination, and no internal
endpoint fallback.

7. **Cross-cutting audit omission and estimate.** Agy never designs the
durable audit path, although every tool call must record key identity, target,
tool, argument digest, and result status. This proposal violates the
constitution: **every tool call is audited**. Put a mandatory audited dispatcher
under all registrations and test denials and failures too. The 15 to 20 hour
estimate is unsupported and omits dependency decisions, encrypted-store crash
and restore tests, sanitized fixtures, audit durability, CI/container work,
Private AI compatibility, and Gate 1 evidence. Claude's 12 to 18 worker-day
range is more credible. Estimate vertical slices with explicit acceptance tests
after the transport and appliance recon spikes.

## Synthesis recommendation

Use Claude's measured fixed-tool, projection, official-SDK, Starlette, and
public-API baseline. Replace its global-only action allowlist with intersected
global and per-key policy, make the audited tool dispatcher structural, persist
one-use plans with apply-time revalidation, use immutable skill versions, and
treat framework, UI, dependencies, and credential encryption as explicit
principal-approved decisions before implementation.
