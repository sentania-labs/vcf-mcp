# Codex worker round 1 architecture proposal

## Evidence and boundaries

I read the project constitution, SPEC v1.0, the VCF Content Factory client and API recon material, the 9.0 and 9.1 OpenAPI files, the files-hosting authentication implementation, and the VMware-AIops public patterns. I did not read another resident's proposal or any summary of one.

I also performed one read-only query against DEVEL: `GET /suite-api/api/actiondefinitions?pageSize=1000`. On 2026-07-20, VCF Operations 9.0.2 returned 142 definitions, all type `UPDATE`, across 10 distinct context adapter/resource-kind pairs. There were 135 single-context definitions and 7 two-context definitions. A definition contains `id`, `displayName`, `type`, action and context kind keys, `contextIds`, `scheduleEnabled`, and `canRecommend`. It contains no input parameter metadata. Parameter `id`, `dataType`, `isRequired`, and `isList` arrive later from action population for selected context resources. This distinction drives fork 1.

This proposal changes no standing ruling. The framework, UI, and cryptography packages are architecture and dependency selections, so the eventual decision records should explicitly record Scott's approval before manifests or production code depend on them.

## 1. Approach

### Fork 1: fixed tools with a catalog-backed action dispatcher

I would expose a fixed client-visible surface, never one tool per action definition. The action family would be six tools: `list_action_definitions`, `populate_action`, `validate_action`, `plan_action`, `apply_action`, and `get_action_task`. Alongside the read-only families and `list_skills`/`get_skill`, this keeps the full server surface small and stable even when installed management packs change the 142-entry catalog.

`src/vcf_ops_mcp/actions/catalog.py` would cache the paginated definition catalog per target for 15 minutes, keyed by target ID and appliance version. It would refresh on expiry, explicit admin target verification, or a requested unknown action ID. Refresh failure may use a last-known catalog for discovery, marked stale, but may not be used to authorize apply. The catalog is descriptive, not policy.

`actions/population.py` would call the population endpoint with the requested action ID and context resource IDs, returning the server-derived method parameter contract and defaults. `actions/validation.py` would reject unknown fields, coerce only unambiguous scalar types, enforce required/list declarations, and then call the VCF Ops validation endpoint. Multi-step `contextIds` remain explicit rather than being flattened.

`actions/plans.py` would persist a short-lived, one-use plan containing a random plan ID, key identity, target ID, action ID, resource IDs, normalized parameter digest, catalog fingerprint, target posture, and expiry. It would return the human-readable summary plus an opaque confirmation token bound by an HMAC to those fields. `apply_action` would accept only that plan ID and token, reload the plan, recheck expiry, API-key scope, target action enablement, the prod hard block, catalog fingerprint, and parameter digest, then atomically consume the plan before executing. It would not accept a fresh arbitrary action payload. Acknowledging an alert and running a report would use the same plan service, not parallel exceptions.

This is preferable to 142 generated tools because tool count and schema context would vary by target and installed packs, while the definitions do not even contain the populated parameter schemas needed to make generated tools accurate. It is preferable to a generic raw REST tool because each operation keeps a narrow schema and auditable policy boundary. Read-only API keys should not see `apply_action` in `tools/list`, but server-side scope and target checks remain authoritative if a client calls it by name.

### Fork 2: official Python SDK, using its bundled FastMCP server layer

I would depend on the official `mcp` Python package and use `mcp.server.fastmcp.FastMCP`, mounted as a Streamable HTTP ASGI application inside one Starlette app. This is the reference SDK's supported high-level layer, not the separately released `fastmcp` package. It provides typed tool, resource, and prompt registration while keeping protocol behavior tied to the official SDK.

`src/vcf_ops_mcp/app.py` would compose `/mcp`, `/admin`, and `/healthz` on one ASGI listener. The MCP application would run stateless HTTP because v1 explicitly excludes sampling and elicitation and stores plans/tasks outside transport sessions. An outer pure-ASGI bearer middleware would parse the presented MCP API key, resolve a principal, attach it to request context, and reject unauthenticated requests before MCP dispatch. Tool wrappers would all pass through one `audited_tool` execution function that records accepted, denied, and failed calls. Authorization would not rely only on SDK OAuth scopes because these are locally minted opaque API keys, not OAuth access tokens.

I would not use the low-level reference server API because it adds protocol plumbing without improving this fixed surface. I would not select standalone FastMCP because its richer middleware and authorization features are unnecessary here and would introduce another framework whose release behavior can diverge from the reference SDK. Before build, pin and smoke-test the selected `mcp` release with Claude Code through fleet-caddy, including initialize, `tools/list`, a tool call, resources, prompts, bearer rejection, and reconnect behavior.

### Fork 3: versioned AES-GCM keyring, encrypted SQLite records, and opaque scoped API keys

`security/keyring.py` would manage a small versioned JSON keyring on the secrets volume, created with an exclusive file operation and mode 0600. Each key is 256 random bits with a non-secret key ID and status. `security/secrets.py` would use `cryptography`'s `AESGCM` with a fresh 96-bit nonce for every credential record. Associated data would bind ciphertext to schema version, target ID, field purpose, and key ID so records cannot be moved or substituted. SQLite stores ciphertext, nonce, algorithm/version, and key ID, never the encryption key. The app refuses to start if ownership or permissions are unsafe, the keyring is absent while ciphertext exists, or decryption integrity fails.

Rotation is online and resumable: add a new active key, keep old decrypt-only keys, re-encrypt each row in bounded transactions with progress recorded in a rotation table, verify every row, then retire the old key. Removal is a separate explicit step refused while any row references the key. Backups must include the database and keyring through a protected operator procedure. Losing the keyring is intentionally unrecoverable, so backup and restore need a Gate 1 test.

This is preferable to Fernet because AES-GCM gives a direct, versioned envelope with associated-data binding and a clearer multi-key rotation model. It is preferable to a single unversioned key file because that makes rotation an outage-prone all-or-nothing rewrite. `cryptography` is a new dependency and therefore requires Scott's approval.

MCP keys would be 256-bit random opaque tokens shown once as `vok_<public-id>_<secret>`. The database stores the public ID, SHA-256 digest of the full high-entropy token, label, creation/revocation/use timestamps, scope enum (`read` or `actions`), and optional target allowlist. Lookup by public ID is followed by constant-time digest comparison. Scope cannot override target posture. An action requires all of: actions-capable key, target allowlist membership if configured, target actions enabled, non-prod target, valid one-use plan, and action-class policy approval. Revocation takes effect on the next request, with no bearer-token cache beyond a single request.

### Fork 4: server-rendered Starlette UI with hardened cookie sessions

I would use Starlette routes and Jinja2 templates rather than a SPA or a second web framework. `admin/routes.py` would implement login/logout, target CRUD and connection test, target posture changes, key mint/revoke, rotation status, and paginated audit views. `admin/forms.py` would parse explicit allowlisted fields. Templates and a small local CSS file would contain no build pipeline and no remote assets.

The files-hosting precedent is sound: hash the bootstrap admin password with scrypt, compare the username in constant time, clear the session on login/logout, use a signed `HttpOnly`, `Secure`, `SameSite=Strict` cookie, reject external `next` targets, return 401 rather than redirects to JSON callers, and protect every management route. For this higher-impact UI I would add a per-session CSRF token checked with constant-time comparison on every state-changing form, rotate the session at login, set a short idle lifetime, and require recent reauthentication for action enablement, key creation, and key rotation.

First boot would accept a bootstrap admin password only through an operator-supplied secret file, hash it into the encrypted store, and delete or invalidate the bootstrap value after successful setup. It must fail closed rather than start with a default credential. The exact slot handoff mechanism remains pending lab-admin facts. Jinja2 and `cryptography` are the only proposed dependencies beyond the official MCP package and its ASGI stack; both need to be named in the decision approval.

I would not use a SPA because the UI has few forms, no rich client state, and no reason to add a JavaScript dependency/build/auth surface. I would not copy Flask from files-hosting because Starlette is already in the official MCP SDK dependency graph and one ASGI stack makes middleware, startup, and deployment simpler.

### Fork 5: immutable skill versions with one canonical renderer

Each skill would live at `skills/<slug>/<semver>/SKILL.md`, with a small checked-in `skills/index.yaml` containing slug, version, title, summary, maturity, source provenance, and content SHA-256. Releases never edit an existing version; they add a version and advance the index's current pointer. A repository validator would enforce safe slugs, semantic versions, unique current entries, existing files, digest agreement, bounded file size, required provenance, and no secrets or lab-specific configuration.

`skills/catalog.py` would load and validate the index at startup into one immutable catalog. All four exposures would render from that same object: resources at `skill://<slug>/<version>`, a current alias at `skill://<slug>/current`, prompts named `use_<slug>` that instruct a client to load the canonical resource, and fixed `list_skills`/`get_skill` tools. `get_skill` accepts slug plus optional version and returns metadata, content, version, and digest. It does not read arbitrary paths. Prompts should reference or return the same content, not maintain a second prompt copy.

Phase 3 mining would add candidates through ordinary reviewed commits with provenance to source repo path and source revision, a portability and secret scan, and a human-edited distillation. It must not mount or scrape the knowledge repos at runtime. Seed skills use the same process now, which ensures Phase 3 scales the catalog rather than redesigning it.

This is preferable to only Git-versioning mutable `skills/<slug>.md` because clients need a stable version and digest they can cite. It is preferable to a database CMS because operational knowledge should remain reviewable, testable, and shipped with the image.

### Fork 6: public-API adapters with capability probes and captured contracts

`vcf/client.py` would own `/suite-api` URL construction, `OpsToken` acquisition, in-memory token storage, one reauthentication attempt after 401, timeouts, TLS verification, and token release at shutdown. Error messages and logs would never include response bodies from authentication. Public `/api/*` is the v1 default. Any `/internal/*` use would live in a visibly separate adapter, add `X-Ops-API-use-unsupported: true`, and require a decision plus an endpoint-specific compatibility test.

`vcf/capabilities.py` would probe `/api/versions/current` and a small read-only endpoint matrix when a target is registered and on demand. It would store the observed release, supported capabilities, last verification, and response-shape fingerprints. Tool handlers call typed domain adapters, not URLs directly. Parsers would require fields needed for safety and tolerate unknown response fields, while never silently inventing missing values. Pagination would be normalized centrally.

Tests would keep synthetic sanitized fixtures for the observed 9.0.2 shapes plus the 9.0 and 9.1 OpenAPI examples. Contract tests against DEVEL would be opt-in and read-only, assert an explicit hostname allowlist, reject every method except GET and the token acquire/release POSTs, and run outside normal CI unless an approved secret is available. No test path knows the prod hostname. A generated OpenAPI diff report would inform adapter work but never generate runtime tools or silently select endpoints.

The first-hour recon should capture and sanitize DEVEL responses for every Phase 1 read endpoint, including pagination and error envelopes, and compare live Swagger if exposed. Existing recon already proves that documented 9.1 internal paths can return 404 on 9.0.2 and that the spec is a floor for some fields, so version strings alone cannot choose behavior. Capabilities must come from safe probes and contract tests.

This is preferable to binding generated models directly to either OpenAPI file because generated clients tend to reject undocumented fields and cannot represent live omissions reliably. It is preferable to broad fallback logic because a wrong fallback can cross from read behavior into mutation. Actions remain disabled until Phase 2 and Scott's gate regardless of what a probe reports.

## 2. Risks

- VCF Private AI Services may impose a tool count, schema subset, resource URI, prompt, authentication, or Streamable HTTP behavior not documented in the available material. The fixed surface minimizes exposure, but an early handshake spike is essential.
- The official SDK's bundled FastMCP layer and ASGI middleware have had rapid release movement. Pinning reduces surprise but increases maintenance responsibility. Pure ASGI middleware should be tested because session-aware BaseHTTP middleware has historically been a fragile integration point.
- The catalog TTL creates a stale-discovery window after management-pack changes. Refusing apply on stale or fingerprint-mismatched catalogs is safer but can temporarily block valid operations.
- Population metadata may contain action-specific data types or defaults that a generic validator cannot model. Passing server validation is necessary, and coercion should be deliberately conservative.
- A one-use plan consumed before upstream submission can leave an ambiguous outcome on a timeout. The audit and plan state model needs an `outcome_unknown` state and must not automatically retry a mutation.
- AES-GCM nonce uniqueness depends on a correct random source, and rotation or restore bugs could make every stored target inaccessible. Synthetic crash tests and a real backup/restore drill are required before Gate 1.
- An app-managed key on a volume protects database-only theft, not compromise of the running container or theft of both volumes. This matches the contract but is not equivalent to a KMS or hardware-backed key.
- Cookie sessions need a signing secret distinct from the credential encryption keys. Bootstrap delivery is not fully decidable until the lab-admin slot handoff arrives.
- A target allowlist on keys is useful least privilege but is more than the SPEC's minimum scope enum. It should remain optional and must not delay Gate 1.
- Immutable skill versions can create repository churn. The validator and current alias must make old versions cheap, while retention policy can wait until actual growth.
- Live response fixtures can contain inventory names or identifiers. Sanitization must replace values while preserving types and cardinality, followed by a secret and hostname scan before commit.
- Reports may be operationally expensive and report generation may mutate server state even though users perceive it as reading. Phase 1 should list definitions only unless recon proves a bounded read-only generation model; otherwise running a report belongs behind the shared plan pipeline in Phase 2.

If I had one hour and one question, I would ask for the exact VCF Private AI Services MCP compatibility envelope, especially maximum tools and JSON Schema features, then spend the hour running a minimal authenticated Streamable HTTP server through that client and fleet-caddy. That is the largest external compatibility risk that local design cannot settle.

## 3. Division-of-labor claim

I am best suited to own the Phase 1 transport and policy spine: the official SDK and ASGI skeleton, opaque-key middleware, audited tool wrapper, and synthetic tests proving read-only structural enforcement. My harness is strong at tracing framework behavior through source, building adversarial authorization tests, and checking that convenient registration mechanisms do not bypass the one audited execution path.

The resident who has the strongest continuity with lab-admin and files-hosting should own deployment and bootstrap handoff, because those facts are still moving and local operational context matters more than generic web expertise. A resident with deeper VCF Content Factory history should own endpoint fixture capture and drift mapping, because recognizing a semantically wrong but syntactically valid VCF response is the hard part there.

## 4. Rough estimate

For Phase 1, I estimate 12 to 18 focused worker-days, parallelizable to roughly 7 to 10 elapsed working days after decisions are approved and the slot handoff exists:

- 2 to 3 days for ASGI/MCP skeleton, bearer authentication, audit wrapper, and client compatibility smoke tests.
- 3 to 4 days for registry, AES-GCM store, bootstrap, rotation skeleton, and failure tests.
- 2 to 3 days for the VCF client, token lifecycle, capability probes, and sanitized fixtures.
- 3 to 4 days for the read-only target, inventory, metrics, alerts, and report-definition adapters and tools.
- 2 to 3 days for the server-rendered admin UI, key management, target verification, and audit view.
- 1 to 2 days for container, CI build, documentation, integration hardening, and Gate 1 runbook. Deployment itself may move to a later round as already allowed.

The estimate grows most if Private AI Services rejects the official SDK's Streamable HTTP/auth shape, live 9.0.2 payloads differ materially across read endpoints, report execution must enter Phase 1, or secure bootstrap/volume handoff facts require a new platform mechanism. Full action execution, plan persistence, API-key action scope enforcement, and task polling are designed here but remain Phase 2 implementation.

## Proposed Phase 1 build sequence for synthesis

1. Record and approve architecture decisions, pin dependencies, and create sanitized DEVEL contract fixtures.
2. Build the single ASGI listener, MCP identity context, structural audit wrapper, health endpoint, and synthetic client smoke tests.
3. Build the target registry, versioned keyring, encrypted credential records, bootstrap admin identity, and backup/rotation tests.
4. Build token lifecycle, capability probes, pagination, error normalization, and target verification.
5. Add fixed read-only tools in vertical slices, each with audit assertions and fixture-backed contracts.
6. Add the server-rendered admin workflows and MCP key lifecycle, keeping every new target read-only.
7. Build the image and CI checks, run through fleet-caddy when the slot handoff is ready, and execute the Gate 1 runbook against DEVEL only.

I found no SPEC contract error requiring an amendment. The report-generation classification needs a decision-record clarification, not a SPEC change: generating a report should be treated as an action if it creates server-side state or material load.
