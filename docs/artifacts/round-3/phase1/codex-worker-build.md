---
source-ref: ae239552ae857294c01adcb4901fc943614ebb20
source-commit: ae239552ae857294c01adcb4901fc943614ebb20
source-blob: 900a8aa7535ba3ca30dbfe8b3c00107faa2f45d5
source-path: docs/proposals/codex-worker-phase1-build.md
worker: codex-worker
round: round-3
phase: phase1
captured: 2026-07-26
---

# Codex worker proposal: Phase 1 read-only build

## 1. Approach

### Build shape and seams

I would divide the implementation into three ownership slices around interfaces,
not around vertical features. The common contracts land first as a small commit,
then the three slices can proceed without editing the same files.

1. **Policy and persistence spine** owns `pyproject.toml`,
   `src/vcf_ops_mcp/config.py`, `db.py`, `migrations/`, `security/keyring.py`,
   `security/api_keys.py`, `targets/repository.py`, `audit.py`, `dispatch.py`,
   and their unit tests. It defines `ToolContext`, `ToolSpec`, `Capability`,
   `TargetRecord`, `TargetPosture`, and repository protocols in
   `src/vcf_ops_mcp/contracts.py`. Nothing else writes SQLite directly.
2. **VCF read plane** owns `src/vcf_ops_mcp/vcf/client.py`,
   `vcf/capabilities.py`, `vcf/projection.py`, `adapters/{inventory,metrics,
   alerts,reports}.py`, and fixture-backed contract tests. Each adapter exports
   `register(registry)` and declares its capability, required key scope, allowed
   HTTP verbs, result cap, and projection version. It receives repository and
   transport protocols from `contracts.py`; it does not import the web app or
   SQLite implementation.
3. **Delivery surfaces** owns `src/vcf_ops_mcp/app.py`, `mcp_server.py`,
   `admin/`, `templates/`, `skills/`, `Dockerfile`, `compose.yaml`, and
   `.github/workflows/build-deploy.yml`. It consumes only the registry and
   repositories. It mounts bundled FastMCP Streamable HTTP, admin routes, and
   `/healthz` in one Starlette lifespan, and uses one canonical skill catalog
   for resources, prompts, `list_skills`, and `get_skill`.

The short common-contract commit is the only planned serialization point. The
obvious alternative, giving each resident a vertical tool family, would make
all three edit app registration, migrations, authorization, audit plumbing,
and transport tests. That creates both merge collisions and three subtly
different enforcement paths.

### Request data flow and structural boundaries

At startup, `app.py` runs migrations, validates the keyring and bootstrap secret
file, loads the immutable skill index, constructs repositories, and registers
adapters. `ToolRegistry.register()` refuses a tool without a capability, scope,
target policy, argument-digest policy, projection, and audited handler. FastMCP
handlers are generated only from this sealed registry. There is no public
decorator or alternate handler map by which a domain function can become an MCP
tool directly.

For a call, the API-key verifier resolves the public key ID and constant-time
checks its digest on every request. The dispatcher then checks revocation,
target allowlist, key scope, global policy, capability registration, and target
existence. It inserts an audit row with status `started` and commits it before
calling an adapter. It finalizes the same row with `succeeded`, `denied`, or a
typed failure after result projection. If the initial insert fails, the adapter
is never invoked. If finalization fails after an upstream read, the client gets
`audit_unavailable`, the durable `started` row remains for reconciliation, and
the result is not returned. This is stricter than best-effort middleware and
matches the fact that one HTTP exchange is not one tool call.

The mutation choke point exists in Phase 1 even though mutation adapters do
not. `vcf/client.py` exposes `request_read()` to normal adapters and keeps
`request_mutation()` private to a future `MutationTransport` that requires a
claimed, typed plan token. The base transport rejects every upstream method
except GET plus the narrowly named token acquire and release paths. The future
mutation transport must also recheck target posture and the prod identity block
immediately before I/O. Tool code cannot supply an arbitrary method. A registry
test walks every Phase 1 adapter and proves its declared upstream verbs are GET.
No Phase 1 capability claims any mutation scope, so the derived grantable-scope
registry cannot offer one in the admin UI.

Record 007 classifies report execution as mutation. Therefore Phase 1 exposes
report definition listing, completed-report listing and metadata, and download
of an existing report, but does not expose report run. Treating report run as a
read because it produces a document would bypass the accepted generalized
mutation gate. This is a contract tension with SPEC's older `list/run/download`
line, but the later accepted record governs it.

### Concrete database and keyring schema

Use one SQLite data database on the data volume and a distinct 0600 keyring file
on its own mount. SQLite is in the Python standard library and keeps migrations,
atomic revocation, audit intent, and admin queries in one transactional model.
`PRAGMA foreign_keys=ON`, WAL mode, a bounded busy timeout, and explicit
transactions are set on every connection.

`schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT, checksum TEXT)`
is append-only. Migration files are numbered SQL plus a Python migration only
where ciphertext transformation is required. Startup refuses a missing,
out-of-order, or checksum-changed applied migration. Migrations run in one
exclusive transaction after an automatic SQLite backup into a dedicated
pre-migration directory on the data volume. Downgrades are refused rather than
attempted.

`targets` contains `id` (random UUID text), `name`, normalized `fqdn`,
`target_type`, `auth_source`, `verify_ssl` (integer constrained to 0 or 1),
`posture` (constrained to `read_only` in Phase 1), `enabled`, encrypted username
envelope, encrypted password envelope, envelope key IDs, `created_at`,
`updated_at`, and optimistic `revision`. FQDN is unique after lowercase and
trailing-dot normalization. URLs, paths, ports, and embedded credentials are
rejected. The production FQDN is tagged with immutable `is_prod=1`; database
constraints and repository checks refuse any posture other than read-only.

Each credential envelope stores algorithm version, key ID, nonce, and
ciphertext. AES-256-GCM AAD is exactly a length-prefixed encoding of schema
version, target ID, field purpose, and key ID. This avoids delimiter ambiguity.
The keyring has a version, one active key, decrypt-only old keys, and rotation
metadata. Absence with an empty new database permits one explicit initialization
path that atomically creates a 0600 file. Absence when any ciphertext exists,
unsafe ownership or mode, unknown key IDs, malformed JSON, duplicate active
keys, or any failed decrypt makes readiness false and startup fail. Corruption
never triggers regeneration. Rotation is resumable in bounded transactions and
old-key removal is refused while referenced.

`api_keys` contains `public_id`, SHA-256 digest bytes, label, `created_at`,
`revoked_at`, `last_used_at`, and optional expiry. `api_key_targets` and
`api_key_scopes` are join tables. `global_scopes` contains the server policy.
Effective authority is always the intersection of non-revoked key scopes,
registered grantable capabilities, global enabled scopes, and target allowlist.
The initial global policy enables only implemented read capabilities. A key
with no rows in `api_key_scopes` can do nothing.

`capability_observations` records target ID, release name, API major/minor,
probe version, capability, observed boolean, shape digest, checked time, and
expiry. Safety-relevant missing fields fail closed. Descriptive extra fields
are tolerated. Version strings are evidence, never behavior switches.

`audit_events` contains an integer sequence, UTC timestamp, correlation ID,
key public ID, target ID, tool name, HMAC-SHA256 argument digest, digest-key ID,
status, normalized error code, latency, projection version, and skill content
digest where relevant. It never stores raw arguments, response bodies,
credentials, or tokens. HMAC rather than bare SHA-256 prevents useful offline
guessing of low-entropy arguments. Audit keys are purpose-separated from
encryption keys in the versioned keyring.

Audit uses a separate SQLite database file on the audit volume so volume policy
and backup are independent from credentials. Rotation is time-based into
read-only monthly SQLite archives using SQLite's backup API, followed by an
integrity check before rows are removed from the live file. Archives are never
automatically deleted in Phase 1. A configured reserve threshold stops new tool
calls before the filesystem reaches zero free bytes. Any write, sync, integrity,
or space failure makes MCP readiness false and calls fail closed; health remains
available so the operator can diagnose it. Admin purge is intentionally absent
from Phase 1 because deleting durable audit history needs a retention decision.

### Token and TLS lifecycle

`TargetClientPool` holds one `httpx.AsyncClient` and one `TokenState` per enabled
target. `TokenState` has token bytes, the acquire time, and a monotonically
increasing generation. Secrets are never placed in exception text, logging
fields, reprs, or audit arguments.

Authentication is single-flight under an `asyncio.Lock`. A caller first checks
the token without locking. If absent, it locks and checks again before acquiring.
Every request snapshots the token generation. On 401, it locks and reacquires
only if the generation still equals the failed snapshot; concurrent callers
then reuse the winner's token. Each original call retries exactly once. A second
401 returns a typed auth failure, never a loop. Token release is best effort at
shutdown and never blocks shutdown indefinitely.

Send the measured canonical header `Authorization: OpsToken <token>`. Do not
depend on the accepted legacy alias. Token acquisition payload includes the
stored `authSource` when configured. Connect, read, write, pool, and total
timeouts are explicit. Error decoding accepts JSON, HTML, or empty bodies but
never logs an auth body.

`verify_ssl=true` uses the system trust store and fails if the certificate is
not trusted. `verify_ssl=false` creates an unverified SSL context for that
target's client only, never changes a process-global warning or environment
setting, and is shown as a persistent warning in target lists, admin pages, and
audit metadata. The current DEVEL certificate did not validate against this
host's system trust, so its honest initial registration will need the explicit
false setting unless the container is given the lab CA. Adding a per-target CA
bundle is a sensible later extension, but it is not silently invented beyond
the required boolean schema.

### Read surface and response control

The tool surface is fixed and narrow: target listing; adapter and resource kind
listing; projected resource search and detail; stat-key discovery; bounded
latest and ranged stats; super-metric listing and detail; alert search/detail
and symptom search/detail; report definition and completed report listing,
metadata, and existing-report download; plus both skill tools. Endpoint names
are not exposed to callers.

Every list has server-owned maximum page size and cursor metadata. Resource,
alert, symptom, and report projections drop HATEOAS links by default and return
only stable identifiers, names, kinds, state, timestamps, and requested metric
values. Full-fidelity output is not a blanket flag. It is a separate bounded
projection per family so a caller cannot recreate the measured 274k-token
resource response. Binary report downloads enforce byte and content-type caps;
oversize files return metadata and a refusal rather than being embedded in MCP
output.

### Hermetic and live verification

CI never receives a VCF credential. Fixture contracts are built from deliberately
small synthetic payloads shaped like the 9.0 OpenAPI and the measured 9.0.2
responses. A local-only `tools/recon_capture.py` accepts credentials from an
operator-owned file, hard-rejects every host except the exact DEVEL FQDN,
hard-rejects methods other than GET plus token acquire/release, projects only
explicitly allowed fields, replaces every identifier, name, hostname, address,
and timestamp with deterministic synthetic values, then scans both values and
raw bytes for the lab domains, usernames, token shapes, IPs, and high-entropy
strings. Raw responses live only in a mode-0700 temporary directory outside the
repo and are deleted by the operator after review. The generated fixture is
still manually reviewed before commit. No capture code knows the PROD FQDN.

Tests include migration upgrade and corruption cases, keyring absence and mode
failures, ciphertext swap/AAD failure, rotation crash-resume, immediate key
revocation, empty-scope denial, target allowlist denial, global-policy
intersection, prod posture constraints, registry refusal for unaudited tools,
audit disk/write failure before invocation, single-flight auth under concurrent
401s, exactly-one retry, per-target TLS isolation, HTML error bodies, pagination
and output caps, missing safety fields, skill path traversal, and MCP initialize,
tools, resources, prompts, bearer rejection, stateless reconnect, and lifespan.

Live verification is a separate operator-run script and checklist. It registers
DEVEL through the admin UI, mints a bounded read key, calls one tool from every
family through the deployed fleet-caddy URL, checks the corresponding audit row,
revokes the key and proves the next request fails, restarts the container and
proves target decryption plus audit continuity, and restores a database backup
with the separately held keyring. It never probes PROD and never mutates DEVEL.

The container build is multi-stage, runs as a non-root fixed UID, has read-only
root filesystem compatibility, mounts distinct data, audit, keyring, and
bootstrap-secret paths, and exposes only the one application port. The workflow
fork-gates jobs, runs lint/tests/skill-index regeneration checks, builds and
pushes `ghcr.io/sentania-labs/vcf-ops-mcp` by immutable commit tag, then deploys
the pinned digest using the onboarded slot's forced-command key from Actions
secrets. It transfers only compose and fleet-caddy slot configuration, never VCF
credentials. Deployment verifies `/healthz` and rolls back to the prior digest
on failed health without touching persistent volumes.

## 2. Risks

- The proposed three slices are uneven. Delivery surfaces combine admin auth,
  MCP behavior, skills, and deployment, and are the most likely schedule tail.
  The seam is clean, but the owner may need to ship admin and MCP first while CI
  support follows immediately after.
- SQLite has one writer. Audit commits on every tool call can become the
  throughput ceiling. WAL and short transactions are adequate for a small lab,
  but this needs a concurrent-call benchmark, especially while the admin UI
  reads the log.
- A durable `started` audit row plus a failed final update proves invocation but
  not outcome. Reads make that acceptable for Phase 1, but it is not sufficient
  for future mutations. The mutation store and audit finalization will need one
  transactional state model before Gate 2.
- Monthly audit archive rotation adds failure modes around backup verification
  and row cutover. If time compresses, the safer reduced scope is no automatic
  rotation plus an early free-space refusal, not lossy deletion.
- `verify_ssl=false` is honest but still vulnerable to interception. The best
  operational result is installing the lab CA in the image or mounted trust
  bundle, but changing deployment trust material should be separately reviewed.
- Report download through MCP may be unusable even with caps, depending on how
  clients render binary resource content. Gate 1 should prove a small real PDF
  download or narrow the tool to metadata plus a server-local retrieval path.
- Fixture scrubbing can miss organization-specific names that do not resemble
  secrets. Allowlist projection before replacement reduces this risk more than
  regex-only redaction, but manual review remains necessary.
- The records settle Jinja2, MCP, Starlette, cryptography, and transitive httpx.
  This proposal assumes no new dependency. If YAML parsing for `skills/index.yaml`
  is not already available, use a JSON-compatible index or a tiny checked-in
  parser format rather than adding PyYAML without Scott's approval.
- SPEC still names report run in the MVP while record 007 classifies it as a
  mutation and this assignment says Phase 1 is read-only. I would implement no
  run path in Phase 1. If the orchestrator reads the contract differently, this
  must be resolved before tool registration, not papered over as a read scope.
- The one-hour, one-question priority is an end-to-end Streamable HTTP smoke
  test through fleet-caddy using the actual Claude Code client. Local SDK tests
  cannot reveal proxy buffering, auth forwarding, reconnect, or client content
  rendering defects, and that single result could reorder the build.

No accepted record is being challenged. The report-run tension above is an
implementation-boundary question created by applying record 007 to Phase 1,
not an attempt to reopen its mutation classification.

## 3. Division-of-labor claim

I am best suited to own the policy and persistence spine: migrations, encrypted
target repository, versioned keyring and rotation, fine-grained scope
intersection, mandatory audited dispatcher, and the structural mutation choke
point. My earlier work produced the four-part AAD binding and identified why
HTTP middleware cannot satisfy per-tool audit, so I have the most context on
the failure cases that make this slice dangerous.

I would not claim the entire read adapter family. A resident strongest at
defensive live-JSON parsing and response projection should own `vcf/client.py`
and the domain adapters, because that slice benefits most from rapid fixture
comparison against OpenAPI drift. Likewise, the resident with the clearest
context on the onboarded docker.int handoff should own the workflow and compose
files. I can review both boundaries, but claiming them would make me the serial
bottleneck and erase the point of three doers.

## 4. Rough estimate

This is roughly 12 to 18 resident-days of implementation and verification:
4 to 6 for policy and persistence, 4 to 6 for client/adapters/fixtures, and 4 to
6 for delivery surfaces, with about 5 to 7 elapsed working days if the common
contracts land on day one and the three slices proceed in parallel. Gate 1
operator verification and any fleet-caddy correction add 1 to 2 elapsed days.

I am most likely wrong about admin session hardening and deploy integration,
not the adapter count. Security edge cases, mounted-file ownership under the
actual container runtime, and proxy behavior tend to consume whole days while
another GET adapter is usually hours.

## Measured findings from DEVEL recon

Measured on 2026-07-21 against only
`vcf-lab-operations-devel.int.sentania.net`, using the delivered read-only
service account. No PROD request was made.

- Token acquisition at `POST /suite-api/api/auth/token/acquire` returned 200.
- `Authorization: OpsToken <token>` returned 200 for
  `GET /suite-api/api/versions/current`. This is the canonical form the server
  should send.
- `Authorization: vRealizeOpsToken <token>` also returned 200 for the same
  request. It is a supported legacy alias, not the selected implementation.
- `Authorization: Bearer <token>` returned 401.
- The version response reported release `VCF Operations 9.0.2.0`, API major 2,
  minor 2.
- With explicit verification disablement for this target, bounded GET requests
  to `/api/adapterkinds`, `/api/resources`, `/api/supermetrics`, `/api/alerts`,
  `/api/symptoms`, `/api/reportdefinitions`, and `/api/reports` all returned
  200. Their top-level collection keys respectively included `adapter-kind`,
  `resourceList`, `superMetrics`, `alerts`, `symptom`, `reportDefinitions`, and
  `reports`; all except adapter kinds also exposed the expected paging wrapper.
- The same version request with the host system CA verification enabled failed
  TLS validation before an HTTP response. This measures the current caller
  trust store, not proof that every deployment image lacks the lab CA.

Inferred, not measured in this recon:

- The appliance likely accepts both auth schemes for compatibility, but no
  promise is inferred about future versions. Record 006 selects `OpsToken`, so
  the implementation sends only that form.
- The seven 200 responses prove reachability and collection envelope names,
  not full schema compatibility, pagination correctness, permission coverage,
  metric query behavior, report download behavior, or 401 refresh behavior.
  Those remain explicit fixture and Gate 1 tests.
