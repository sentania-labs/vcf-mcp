# Phase 1 consensus build spec

Round 3 synthesis. This is the agreed design for the Phase 1 read-only build of
vcf-mcp. It is a specification, not code: nothing in it has been
implemented. It is the deliverable of GitHub issue #2 and it waits for the
principal's approval there.

Authority for every decision in this document is
`docs/decisions/009-phase1-build-synthesis.md`, which carries the ballots, the
critic's tiebreaking vote, and every losing objection verbatim. Where this
document and record 009 differ, record 009 governs.

Standing records this build implements without reinterpretation: 001 (action
tool surface and the mandatory audited dispatcher), 002 (MCP framework and
transport), 003 (credential store and API keys), 004 (admin UI stack), 005
(skills content model), 006 (API version drift), 007 (mutation gate
generalization), 008 (alerts read-only in the MVP).

## 1. Shape

One Python 3.12 package `src/vcf_mcp/` in one container, one uvicorn
process, one Starlette parent app mounting three children:

- FastMCP's `streamable_http_app()` at `/mcp`, Streamable HTTP, API-key auth
- the Jinja2 admin UI at `/admin`
- `/healthz`

Four layers beneath, with narrow seams: a **store** layer (SQLite plus the
AES-256-GCM envelope), a **vcf** layer (one client per registered target, owning
`/suite-api` URLs and the token), a **dispatcher** (the single mandatory
audited, authorized entry point), and a **tools** layer of thin read-only
handlers structurally incapable of reaching the network except through a typed
domain adapter.

Three volumes, not two, per record 003's separation controls: `/data` (the
SQLite data database), `/keys` (the keyring, 0600, distinct ownership, excluded
from the data database's backup artifact), `/audit` (the audit database).
Container runs non-root at a fixed UID with a read-only root filesystem.

## 2. Measured facts this design is built on

Every item was measured against `vcf-lab-operations-devel.int.sentania.net`
during round 3 with the delivered read-only service account. Nothing was
measured against PROD. These are the constants the implementation must not
re-derive from documentation.

| Fact | Value | Consequence |
| --- | --- | --- |
| Inventory scope (re-verified 2026-07-24) | 517 resources, 21 adapter kinds | Gate 1 is meaningful; payload caps are load-bearing |
| Auth scheme | `OpsToken` and `vRealizeOpsToken` both 200; `Bearer` and arbitrary schemes 401 | Send `OpsToken` per record 006; the alias is a comment |
| Token TTL | 6.0 hours, `validity` is absolute epoch ms | Refresh at TTL minus a 5-minute skew margin |
| Token independence | Repeated acquires return distinct tokens; old tokens stay valid; release does not disturb siblings | A re-auth storm is wasteful, not dangerous |
| `roles` in the acquire response | Empty array | Never use it for authorization |
| Wrong `authSource` versus wrong password | Byte-identical 401 | Unfixable at the API layer; mitigate with a picker |
| 401 versus 403 | `POST /api/events/query` returns 403 with an HTML body for ReadOnly | Re-auth on 401 only; 403 is a permission error naming the endpoint |
| Error body content type | Invalid token yields JSON, bad scheme yields HTML | Error decoding must not assume JSON |
| Read families and verbs | Every Phase 1 read family has a working GET form; `/query` endpoints are POST | GET-only is buildable but is the wrong predicate |
| GET URI ceiling | 500 resource ids, 24,027 bytes of query string, still 200 | URI length does not bind at Phase 1 scale |
| **Unknown query parameters** | **Silently ignored; returns the unfiltered collection with a 200** | **The parameter allowlist in section 4 is mandatory** |
| `stats/query` size | 137,808 bytes for one resource at `maxSamples=1` | Metrics is the payload blowup risk, not `/resources` |
| Pagination | `pageInfo {totalCount, page, pageSize}`; a `NEXT` link is present even on a single-page result | Compare `(page+1)*pageSize` against `totalCount` |
| Version reporting | `releaseName` "VCF Operations 9.0.2.0", `major/minor` 2/2 | Never parse `releaseName` to select behavior |
| Unauthenticated surface | `GET /api/auth/sources` and `GET /api/deployment/node/status` answer 200 with no `Authorization` header | Registration can enumerate real auth sources before a credential is typed |
| TLS | DEVEL presents a self-signed certificate; the default context fails `CERTIFICATE_VERIFY_FAILED` | See section 7; this is an open question for the principal |
| Collection envelope keys | `adapter-kind`, `resourceList`, `superMetrics`, `alerts`, `symptom` (singular), `reportDefinitions`, `reports` | Verified independently by two doers |
| `GET /api/reports` on DEVEL | `totalCount: 0` | See section 6; there is nothing to demonstrate |

## 3. The dispatcher

Every tool call passes through one dispatcher. Record 002 already ruled out HTTP
middleware as the audit boundary, because a Streamable HTTP request count is not
a tool-call count.

**What makes it mandatory is registration, not convention.** Tool handlers are
never passed to FastMCP directly. A handler declares itself into a
module-level registry; at startup the registrar walks the registry and registers
a *generated* wrapper closure that calls the dispatcher. The raw handler is
never the object FastMCP holds. A handler that forgets the dispatcher is not an
unaudited tool, it is a tool that does not exist: it never appears in
`tools/list` and cannot be called. The failure mode of forgetting is
invisibility, not silent unaudited execution.

Three controls back that, per record 009 decision 5:

- The raw FastMCP instance is **not** exported to tool modules. Construction and
  binding live in one composition root and only the project's registrar is
  exposed.
- An end-to-end test observes an audit record for **every** listed tool. This,
  not the registry comparison, is the security boundary.
- The assertion comparing the project registry against FastMCP's private tool
  manager is retained as a **tripwire only**, with its dependency-private nature
  documented at the assertion, since it reaches into `mcp._tool_manager`.

`ToolRegistry.register()` refuses any tool lacking a capability, key scope,
target policy, argument-digest policy, projection, outbound contract, and
audited handler.

Per call, in order:

1. Resolve key identity from the request-scoped access token (record 002's
   `TokenVerifier`). Constant-time digest comparison on every request.
2. Check revocation, then the key's target allowlist, then target existence.
3. Check the tool's capability against the key's granted scopes intersected with
   global policy. **Default deny.** A key with no granted scopes can do nothing.
4. Check target posture against the capability (section 4).
5. Write and **commit** the `attempt` audit record. If this write fails, the
   call is refused and the handler never runs.
6. Run the handler with a deadline.
7. Project and cap the result (section 5).
8. Write the terminal audit record: `ok`, `denied`, `error`, `timeout`, or
   `outcome_unknown` (section 8).

## 4. Read-only enforcement

Two independent layers, neither of which keys on the HTTP verb.

### 4.1 Authorization: semantic capability, default deny

```python
class Capability(StrEnum):
    READ_INVENTORY = "read:inventory"
    READ_METRICS   = "read:metrics"
    READ_ALERTS    = "read:alerts"
    READ_REPORTS   = "read:reports"
    READ_SKILLS    = "read:skills"
    READ_TARGETS   = "read:targets"

MUTATING: frozenset[Capability] = frozenset()   # empty in Phase 1, on purpose
```

The dispatcher refuses any tool whose capability is not declared, and refuses
any tool whose capability is in `MUTATING` unless the target posture is
`actions_enabled`. In Phase 1 that branch never fires in production, which is
the point: the branch exists, sits on the mandatory path, and is tested before
there is anything for it to stop. Adding an action capability in Phase 2 is
adding a name to a set, not building a gate.

Three defense layers, per record 009:

1. **Schema.** `CHECK (NOT (is_prod = 1 AND posture = 'actions_enabled'))`. A
   prod target cannot be actions-enabled at rest, whatever any code path
   believes. `is_prod` is set by matching the FQDN against a checked-in constant
   list containing `vcf-lab-operations.int.sentania.net`, evaluated at insert
   **and** re-evaluated at every startup, so renaming a row cannot launder a
   prod appliance into a devel one.
2. **Dispatcher.** The capability/posture check above.
3. **Grantable-scope derivation.** The grantable scope set is derived at startup
   from registered adapters. No mutating adapter is registered in Phase 1, so no
   mutating scope exists, so the admin UI cannot render it and a key cannot hold
   it.

**Both mutation tests ship.** A test-only mutating capability is registered in a
test-scoped registry and run through the real dispatcher against read-only,
actions-enabled, and prod fixtures, asserting deny, allow, deny. Separately, a
production assertion that `MUTATING == frozenset()` is retained as a tripwire,
because adding a mutating capability then requires deleting an assertion that
says there are none, which is a visible and greppable act in a diff.

### 4.2 The outbound contract: a frozen (method, path, parameter) allowlist

Every tool declares, at registration, the exact HTTP method, path template, and
**permitted query parameter names** its adapter may use. The registry freezes
the union. The transport refuses any call outside the frozen set and tool code
cannot supply an arbitrary method, path, or parameter.

The parameter half is not decoration. The appliance silently ignores
unrecognized query parameters and returns the unfiltered collection with a 200:
`?identifier=<uuid>`, a plausible misspelling of `?resourceId=`, returns the
whole collection rather than one object. Against 517 objects that is record
001's token blowup reached by a one-word typo, with the response correctly
shaped, correctly paginated, correctly projected, and the wrong scope. No
fixture test can catch it, because a mock answers whatever URL it is handed.
**The live tier (section 9) is the only place this is validated, and validating
it is a required live-tier assertion, not an optional one.**

The transport exposes `request_read()` to adapters. A future `request_mutation()`
stays private to a Phase 2 transport requiring a claimed, typed plan token, and
must recheck target posture and the prod identity block immediately before I/O.

## 5. The read surface

Endpoint names are never exposed to callers. Every list has a server-owned
maximum page size and cursor metadata.

| Family | Capability | Tools |
| --- | --- | --- |
| targets | `read:targets` | list registered targets and their posture |
| inventory | `read:inventory` | list adapter kinds, list resource kinds, search resources (projected), resource detail |
| metrics | `read:metrics` | discover stat keys for a resource, latest stats (bounded), ranged stats (bounded), list super metrics, super metric detail |
| alerts | `read:alerts` | search alerts, alert detail, search symptoms, symptom detail. **Read-only, no mutation verb, per record 008** |
| reports | `read:reports` | report definition listing. See section 6, this family is scoped down and is an open question for the principal |
| skills | `read:skills` | `list_skills`, `get_skill` |

Auth and session (token acquire and refresh) is not a tool family. It is
internal to the client and invisible to MCP clients, per SPEC 4.1.

**Projection and caps.** Resource, alert, symptom, and report projections drop
HATEOAS links by default and return stable identifiers, names, kinds, state,
timestamps, and requested metric values. Full fidelity is not a blanket flag; it
is a separate bounded projection per family, so a caller cannot reconstruct the
274k-token response record 001 measured.

**Metrics is the payload risk and it is bounded by refusal, not truncation.**
`stats/query` returned 137,808 bytes for one resource at `maxSamples=1`. A
mandatory server-side cap applies to the product of resource count, stat-key
count, and sample count, and exceeding it returns an **explicit refusal naming
the cap** rather than a silently truncated series. Silently truncated metric
data is worse than no metric data. The per-family sample cap is the concrete
reason the registration record must be an open versioned mapping (section 10).

## 6. Reports, and why the family is nearly empty

Record 007 classifies report run as a mutation, so Phase 1 ships no run path.
That leaves definition listing, completed-report listing, and download of an
existing report.

`GET /api/reports` on DEVEL returns `totalCount: 0`. There are no completed
report instances, and creating one is a mutation nobody is authorized to perform
in Phase 1. So of the three surviving capabilities, one works, one returns an
empty list, and one has nothing to operate on. codex-worker separately flags
that binary report download through MCP may be unusable regardless, depending on
how clients render binary resource content.

**This spec ships report definition listing only.** Completed-report listing and
download are deferred to Phase 2, where they land alongside the run path that
makes them demonstrable. This is a reduction against SPEC 4.1's
`reports: list/run/download` line and it is flagged to the principal on issue #2
rather than taken as a team decision, because it changes the delivered MVP
surface. If the principal prefers the full listing and download surface built
now against an empty appliance, the workplan absorbs roughly one additional
dispatch-day in the read plane.

## 7. Client, tokens, and TLS

One client per registered target, held in a process-level registry keyed by
target id, built lazily, owning an `httpx.AsyncClient` (already in the `mcp`
dependency graph per record 002, so not a new dependency).

**Token acquisition is single-flight.** A caller checks the token without
locking, then locks and re-checks before acquiring. Refresh happens at
`expires_at` minus 300 seconds against the measured 6-hour TTL.

**A 401 storm produces exactly one re-acquisition.** Each caller captures the
auth generation before issuing its request. On 401 it takes the lock and
re-checks whether the generation still equals its snapshot; only the first
arrival matches, re-acquires, and bumps the generation. The others find the
generation moved and retry with the winner's token.

**Retry is bounded by an explicit per-request counter, not by the generation
counter alone.** The generation is a property of the interleaving; under
mid-session credential revocation it keeps moving for reasons unrelated to this
request, and a caller can keep finding a "fresh" token that also 401s. An
integer on the request object makes "exactly once" a checked property. A second
401 is a typed terminal error.

**Re-auth triggers on 401 only.** Never 403. A client that treats "auth-ish
non-2xx" as expiry burns an acquire on every events call forever.

**A separate target-configuration generation** is checked before retry and
before returning a result. On a target edit the old client is marked closed and
its in-flight work is drained or cancelled under documented semantics.
Otherwise an in-flight request keeps using superseded credentials and superseded
TLS policy against a target the operator believes they just changed, and an
operator flipping `verify_ssl` from false to true is performing a security
action that must not be silently ignored.

Token release at shutdown is best effort and never blocks shutdown
indefinitely. Connect, read, write, pool, and total timeouts are explicit.
Secrets never appear in exception text, log fields, reprs, or audit arguments.

**TLS.** Per-target configuration on that target's own client, never a
process-global disable. DEVEL's certificate does not validate against the host
trust store, so the honest first registration is verification disabled, which
codex-worker correctly notes exposes credentials and tokens to a local network
attacker. **The clean answer is a mounted lab CA bundle, which is a deployment
trust-material change and therefore the principal's call.** This spec ships the
per-target boolean and carries the CA bundle as an open question on issue #4 of
the TLDR. Fingerprint pinning is **not** budgeted: normal validation cannot
complete a handshake against an untrusted self-signed chain and then perform a
post-handshake fingerprint check, so a correct pinning implementation is a
purpose-built transport plus an explicit unauthenticated first-trust ceremony,
and that is its own slice.

## 8. Audit

**Storage:** a SQLite database on the audit volume, distinct from the credential
store's database, WAL mode, bounded busy timeout, explicit transactions. **No
automatic rotation ships in Phase 1.** Admission of new tool calls stops at a
conservative free-space threshold. Retention and archival are a later decision.

**Record fields:** an integer sequence, UTC timestamp, correlation id, key
public id, target id, tool name, **HMAC-SHA256** argument digest with a
purpose-separated digest key, status, normalized error code, latency, projection
version, and skill content digest where relevant. Never raw arguments, response
bodies, credentials, or tokens. HMAC rather than bare SHA-256 because Phase 1
arguments are low-entropy (a resource kind from 21 adapter kinds, a stat key
from an enumerable set) and a bare digest is enumerable offline by anyone
holding the log.

**Ordering and failure semantics:**

- The `attempt` record is written and committed **before** the handler runs. If
  that write fails, the call is refused. A writability *check* is not a write;
  the space can vanish between check and append, and the tool call itself may be
  what consumes it.
- If the **terminal** write fails after the upstream call already succeeded, the
  dispatcher returns a typed **`outcome_unknown`** state, carrying the result
  payload in a **subordinate field** rather than the success position,
  prohibiting automatic client retry and saying why, forcing readiness false,
  and surfacing the call for reconciliation from durable storage. On recovery,
  `started` rows with no terminal record are closed as `outcome_unknown`, never
  optimistically marked successful.
- **Audit unavailability does not block process startup.** The process starts,
  `/healthz` and the admin UI stay up and report the degraded state, MCP
  readiness is false, and every tool call fails closed.
- **Binding rider:** while audit is degraded, security-relevant admin **writes**
  (register or edit a target, change posture, mint or revoke a key, rotate the
  keyring) fail closed exactly as tool calls do. The admin UI stays available
  for diagnosis and reading, never for unaudited change.

**The invariant reading**, stated so the principal can overrule it: the
constitution's audit invariant is satisfied by a durable pre-execution record,
plus an honestly-typed unknown outcome, plus reconciliation, plus fail-closed.
No implementation can promise a durable terminal write through physical media
failure, and withholding the result fails the same clause in exactly the same
way while additionally losing the caller's data. This is a named item in the
Gate 1 review packet.

## 9. Store, keys, and startup

One SQLite data database on `/data`. `PRAGMA foreign_keys=ON`, WAL, bounded busy
timeout, explicit transactions. `schema_migrations` is append-only with a
checksum per applied version; startup refuses a missing, out-of-order, or
checksum-changed applied migration. Migrations run in one exclusive transaction
after an automatic backup into a pre-migration directory. Downgrades are refused
rather than attempted.

`targets` carries a random UUID id, name, normalized FQDN (lowercased, trailing
dot stripped, URLs, paths, ports, and embedded credentials rejected, unique),
target type, auth source, `verify_ssl`, posture constrained to `read_only` in
Phase 1, enabled flag, **encrypted username and password envelopes**, envelope
key ids, timestamps, an optimistic `revision` column, and `is_prod`. The
username is encrypted alongside the password: it is not a secret the way a
password is, but it is lab-identifying material in a database whose purpose is
to not leak lab-identifying material.

Each envelope stores algorithm version, key id, nonce, and ciphertext. AES-256-GCM
AAD is a **length-prefixed** encoding of schema version, target id, field
purpose, and key id, avoiding the delimiter ambiguity a `|`-joined string has.
The keyring is versioned with one active key and decrypt-only old keys. A
ciphertext moved between target rows must fail to decrypt, and that is an actual
test.

`api_keys` stores public id, SHA-256 digest bytes, label, timestamps, revocation
and optional expiry, with `api_key_targets` and `api_key_scopes` join tables and
a `global_scopes` policy table. Effective authority is always the intersection
of non-revoked key scopes, registered grantable capabilities, global enabled
scopes, and the target allowlist. The initial global policy enables only
implemented read capabilities.

**Startup keyring states**, fail-closed and never regenerating over ciphertext:

| State | Behavior |
| --- | --- |
| No keyring, no ciphertext rows | One explicit atomic initialization path creates a 0600 keyring. First boot. |
| No keyring, ciphertext rows exist | **Refuse to start**, naming the expected keyring path |
| Keyring present, wrong mode or ownership | **Refuse to start** |
| Keyring present, one row fails to decrypt | Start; mark that target unusable and surface it in the UI |
| Keyring present, **every** row fails | **Refuse to start.** This is a wrong-volume situation, not a data situation |

Rotation is resumable in bounded transactions; removing an old key is refused
while it is still referenced.

## 10. Decomposition

Three slices around an interface spine, plus skills. `contracts.py` lands first
as a short commit and is the only planned serialization point.

**The registration record is an open, versioned mapping with a small required
core**, not a fixed signature. A per-family declaration field (the metrics
per-call sample cap is the concrete case) is then an additive adapter change
plus a dispatcher reader, rather than a recurring three-way edit on the hottest
file in the tree. Section 4.2's `(method, path, parameters)` triple adds three
fields on day one, which is why this matters immediately.

| Slice | Owner |
| --- | --- |
| Policy and persistence spine, including sole ownership of the dispatcher package | codex-worker |
| VCF read plane | claude-worker |
| Delivery surfaces | agy-worker |
| Skills | agy-worker, as a distinct workplan item with distinct review, explicitly non-blocking relative to the Gate 1 deploy |

Shared ownership of the dispatcher is rejected: "assemble last" leaves the
integration of the most correctness-critical file in the tree with no owner, and
the only party positioned to do it is the orchestrator, which is forbidden to
write code. One resident owns it and publishes narrow protocols first.

## 11. Testing

**Tier 1, unit, in CI, no network.** Crypto envelope round-trip and AAD
rejection, key derivation, constant-time comparison, the dispatcher's
authorization chain against a fake store, projection, canonicalization, audit
record shape, migration upgrade and corruption, keyring absence and mode
failures, rotation crash-resume, immediate key revocation, empty-scope denial,
target allowlist denial, global-policy intersection, prod posture constraints,
registry refusal for unaudited tools, and the test-only mutating capability
through the real dispatcher.

**Tier 2, contract, in CI, no network, fixtures only.** `httpx.MockTransport`
over generated fixtures, exercising the full client: the 401 re-auth path
asserting **exactly one** acquire across N concurrent callers, the 403 path
asserting **no** re-auth fires, the per-request retry bound, target-edit drain
semantics, HTML error bodies, pagination, output caps, audit write failure
before invocation, disk exhaustion, concurrent writers, busy timeouts, crash
recovery, skill path traversal, and MCP initialize, tools, resources, prompts,
bearer rejection, stateless reconnect, and lifespan.

**Tier 3, live contract, never in CI, opt-in, budgeted.** `pytest -m live`
against DEVEL, run by a resident on demand, at every gate, and after every
appliance upgrade. Guarded mechanically: a session-scoped fixture asserts the
configured host is on an allowlist that **does not contain the prod FQDN**, and
an httpx event hook raises on any method or path outside the enumerated read
set. A live test that tries to mutate fails as a test error, not as a mutation.

**This tier is a named workplan item, not a convenience.** It is the only thing
that detects appliance drift, and it is the only place section 4.2's parameter
allowlist can be validated against reality. Contract tests assert shape,
required-field presence, and monotonic properties; **they never assert exact
object counts**, since the inventory moved from 4 to 517 inside one round.

**Fixtures.** No raw captured byte is ever committed. Raw captures live outside
the repository worktree entirely. The generator projects an explicit allowlist
of response **schema paths**, substitutes **deterministic pseudonyms that
preserve reference equality** (a resource id appearing in an object and again in
its links must remain the same value, or identity and link parsing cannot be
tested), rejects unknown keys and value classes, and emits metadata carrying
generator version, source API version, and generation date. A proof test asserts
no raw capture token appears in output. A CI scanner over the fixture tree looks
for the lab domain, RFC1918 addresses, the prod hostname, and high-entropy
strings, as a backstop rather than the primary control. A fixture-freshness
check runs at the release gate.

## 12. Skills

Straight implementation of record 005: immutable `skills/<slug>/<semver>/SKILL.md`,
a CI-generated index validated by exact regeneration, one catalog object loaded
and digest-verified at startup, and four exposures rendering from it (the
`skill://<slug>/<version>` resource, the `current` alias, the `use_<slug>`
prompt, and the `list_skills` / `get_skill` tools). `get_skill` serves only from
the in-memory index and never touches a path derived from an argument. The dev
path override exists, defaults off, and refuses to load if any registered target
is actions-enabled.

Seed content is SPEC 4.2's three skills. The suite-api auth walkthrough is
authored by claude-worker from its measured recon, which is the most accurate
description of that appliance's auth behavior this team has, and handed to the
skills owner as content. That is content authoring, not co-ownership.

If YAML parsing for the index is not already available in the dependency graph,
use a JSON-compatible index format rather than adding PyYAML: a new dependency
is an escalation.

## 13. Admin UI

Record 004's stack and its full hardening list: scrypt, per-session CSRF,
session rotation, short idle lifetime, and recent-reauth before sensitive
operations. Forms for target registration and editing, the per-target
read-only/actions toggle (with the prod hard-block enforced in schema as well as
in the route), API-key minting and revocation, and the audit log view.

**The auth-source field is a picker, not free text**, populated from the
target's own unauthenticated `GET /api/auth/sources` at registration time, plus
an explicit "Local users" entry because the local source does not appear in that
list. This does not fully solve the byte-identical 401 for a wrong auth source;
it removes most of the failure mode and the remainder is an accepted limitation.

The audit view reads the audit database directly, which is one of the reasons
decision 2 chose SQLite: an NDJSON log needs a reader written first, and that
reader lands in the slice that is already the largest.

## 14. CI, container, deploy

Two workflows, fork-gated per the constitution, on self-hosted runners. CI on PR
and push runs lint, tiers 1 and 2, the fixture scanner, the fixture-freshness
check, and the skills index exact-regeneration check. Release on merge to `main`
builds one multi-stage image and pushes
`ghcr.io/sentania-labs/vcf-mcp:<sha>`, then deploys the pinned digest to the
docker.int slot using the onboarded slot's forced-command key from repo Actions
secrets, per the `ai-log-depot` standard and the lab-container-host contract's
multi-tenant slot model.

**CI never holds a VCF credential**, and there is nothing for it to hold: targets
are configured post-deployment through the admin UI. Deployment transfers only
compose and slot configuration. It verifies `/healthz` and rolls back to the
prior digest on failed health without touching persistent volumes. Image tags
are pinned; `:latest` never appears in compose.

## 15. Gate 1

Gate 1 is the principal connecting Claude Code to
`https://vcf-mcp.int.sentania.net` with a minted read-only key and running
read queries against DEVEL. The review packet carries, as named items:

1. One tool call from every implemented family, with the corresponding audit row
   shown.
2. Key revocation proving the next request fails.
3. A container restart proving target decryption and audit continuity.
4. A database restore with the separately held keyring.
5. **The audit invariant reading from section 8**, for the principal to confirm
   or overrule.
6. **The TLS question from section 7**: ship the per-target verification-disabled
   boolean for the lab, or mount a lab CA bundle.

Two day-one spikes precede the build proper, because three designs depend on
mechanisms nobody has verified:

- **FastMCP identity injection.** Every design assumes the API-key identity
  resolved in ASGI middleware is available inside the tool handler. If it is
  not, every audit record and every authorization check rests on an identity
  that is not there at the point of use. An afternoon to prove, and it gates the
  dispatcher.
- **An end-to-end Streamable HTTP smoke test through fleet-caddy** with the
  actual client. Local SDK tests cannot reveal proxy buffering, auth forwarding,
  reconnect, or client content rendering defects, and that single result can
  reorder the build.
