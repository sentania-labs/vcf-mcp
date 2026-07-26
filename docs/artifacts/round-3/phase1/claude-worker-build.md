---
source-ref: bfc23827ee5fa47e169a7c0059414c2688d25060
source-commit: bfc23827ee5fa47e169a7c0059414c2688d25060
source-blob: dadf547cca0dc05eb634ec672ef411b727add46a
source-path: docs/proposals/p1-build-claude.md
worker: claude-worker
round: round-3
phase: phase1
captured: 2026-07-26
---

# Phase 1 build proposal, claude-worker

- **Round:** vcf-ops-mcp Phase 1, read-only tool families against DEVEL
- **Dispatch:** `vom-p1-prop-claude-20260721-195243`
- **Branch:** `claude/p1-build`
- **Author:** claude-worker
- **Written blind.** I read records 001 through 008 and `docs/SPEC.md`, did my
  own read-only recon against DEVEL, and read no peer proposal, branch, or
  worktree.

---

## 0. Measured findings from DEVEL

Everything in this section I ran myself against
`vcf-lab-operations-devel.int.sentania.net` on 2026-07-21 with the delivered
`vcf-ops-mcp` ReadOnly service account. Nothing was run against PROD, not a
read, not a probe. No token or password value appears here or in any file I
committed. Inferences are marked as such and kept separate.

### 0.1 The auth-header discrepancy: both strings work, and the assignment's is correct

This was the thing I was told to measure rather than guess, so I measured it
directly and then measured what is actually being validated.

| `Authorization` value | `GET /suite-api/api/versions` |
| --- | --- |
| `OpsToken <token>` | **200** |
| `vRealizeOpsToken <token>` | **200** |
| `opstoken <token>` (lowercase) | **200** |
| `Bearer <token>` | 401 |
| `Garbage <token>` (valid token, unknown scheme) | 401 |
| `<token>` (bare, no scheme) | 401 |
| `vRealizeOpsToken <tampered token>` | 401 |
| (header absent) | 401 |

**Resolution: the two sources are not in conflict, they are aliases.** The
appliance accepts an allowlist of scheme names, case-insensitively, and both
`OpsToken` and `vRealizeOpsToken` are on it. An arbitrary scheme is rejected,
so this is an allowlist and not "the scheme is ignored".

So the assignment is right, the credentials file header comment is right, and
record 006 is right to say send `OpsToken` as the canonical 9.x scheme rather
than the legacy alias. **We send `OpsToken`.** I record the alias only so that
a later reader debugging against vcf-content-factory (whose `client.py` line 94
sends `vRealizeOpsToken`) does not think one of the two is a bug.

The 401 bodies differ by cause and this matters for the client: an invalid
token returns a **JSON** error envelope, while a bad scheme returns **HTML**.
Record 006 already anticipated exactly this ("error decoding must not assume
JSON") and my measurement confirms it on the auth path specifically.

### 0.2 Token lifecycle, measured

| Property | Measured value |
| --- | --- |
| Acquire body key | `password` (not `pass`) |
| Acquire response keys | `token`, `validity`, `expiresAt`, `roles` |
| Token TTL | **6.0 hours** (`validity` is absolute epoch ms) |
| `roles` in acquire response | `[]`, empty, **do not use it for authorization** |
| Repeated acquires | each returns a **distinct** token |
| Old token after a new acquire | **still valid** (no implicit single-session invalidation) |
| 5 rapid sequential acquires | all 200, all distinct, all simultaneously valid, 0.9 s total |
| `POST /auth/token/release` | **200**, empty body; that token then 401s |
| Release side effect on sibling tokens | **none**, siblings stay valid |
| Wrong password | 401, JSON envelope |
| Wrong `authSource` (`"ad"` for a local user) | **401, byte-identical message to wrong password** |

Two of these have direct design consequences and I build on them below:

- **Tokens are cheap and independent.** A thundering-herd re-auth is not
  *dangerous* on this appliance (no session cap was hit at 5 concurrent, no
  invalidation of siblings). It is merely wasteful. That downgrades fork 3's
  concurrency question from a correctness problem to an efficiency one, which
  changes what the right fix costs.
- **A wrong auth source is indistinguishable from a wrong password.** This is
  the single nastiest operator trap in the whole Phase 1 surface, and it lands
  squarely in the admin UI's target-registration form. Designed for below.

### 0.3 The service account's object scope is a Gate 1 blocker

This is the finding I would most want the orchestrator to act on today, ahead
of any decomposition argument.

```
GET /suite-api/api/auth/currentuser
  roleNames: ["ReadOnly"]
  role-permissions: [{roleName: "ReadOnly",
                      scopeId: "cde5bb6a-...",
                      allowAllObjects: false}]

GET  /suite-api/api/resources?pageSize=100   -> totalCount: 4
POST /suite-api/api/resources/query {"resourceKind":["VirtualMachine"]} -> totalCount: 0
GET  /suite-api/api/alerts?pageSize=1        -> totalCount: 7
GET  /suite-api/api/adapterkinds             -> 21 adapter kinds
```

The four visible resources are `Universe`, `Container`, `Entire Enterprise
Applications`, and one `VMWARE_INFRA_MANAGEMENT_INSTANCE`. **Zero virtual
machines. Zero hosts. Zero datastores.**

Compare record 001's measured `508 resources / 1,097,361 bytes`. That number
was measured last round against a *different, wider* credential. The service
account we were actually delivered does not see that inventory.

Gate 1 is "Scott connects Claude Code with a minted read-only key and runs read
queries against DEVEL". With this account, `query_resources` returns four
container objects and a VM query returns nothing. The server would be working
perfectly and the gate would look like a failure.

**Inference, not measurement:** the fix is a lab-admin change to the
`vcf-ops-mcp` user's role scope (`allowAllObjects: true`, or a scope covering
the vCenter adapter instances). I did not attempt it; that is a write to the
appliance and outside my authority. I recommend the orchestrator raise a
cross-workspace request to lab-admin **now**, in parallel with the build, since
the round-trip is likely slower than the code.

I also note this quietly invalidates the "field projection saves 92%" sizing in
record 001 *for our account* (I measure 57% HATEOAS `links` share on the 4-row
page, and 8,116 bytes to 2,124 under a three-field projection, a 74%
reduction). Projection is still obviously right. Its measured payoff will only
be re-observable once the scope is widened.

### 0.4 Reads are POST. Verb-based read-only enforcement is unbuildable.

| Call | Result |
| --- | --- |
| `POST /api/resources/query` | 200 |
| `POST /api/resources/stats/query` | 200, 137,808 bytes for one resource, `maxSamples=1` |
| `POST /api/alerts/query` | 200 |
| `POST /api/auth/token/acquire` | 200 |
| `POST /api/events/query` | **403** (ReadOnly lacks the privilege) |

Three of the four core read families are HTTP POST. Any read-only choke point
that keys off HTTP method is either wrong or useless. This is load-bearing for
section 4 below.

`stats/query` returning 137 KB for a **single** resource at `maxSamples=1` is
the other number worth staring at. That is the payload-size risk in Phase 1,
not `/resources`.

### 0.5 403 is not 401, and re-auth must not fire on it

`POST /api/events/query` returns **403 with an HTML body** for our ReadOnly
account. A client that treats "not 2xx and auth-ish" as "token expired,
re-acquire and retry" will, on every single events call, burn an acquire, retry,
get 403 again, and log an auth failure that has nothing to do with auth.
Re-auth fires on **401 only**, once, and 403 is surfaced as a permission error
naming the endpoint.

### 0.6 Unauthenticated surface

`GET /api/auth/sources` and `GET /api/deployment/node/status` both answer
**200 with no `Authorization` header at all**. Everything else I probed
(`/versions`, `/versions/current`, `/resources`) is 401 without auth.

This is useful, not alarming: **target registration can validate the FQDN and
enumerate the appliance's real auth sources before the operator has typed a
credential.** The measured sources on DEVEL are `All vCenters` (VC_GROUP),
`vcf-lab-wld01` (VC), `ad` (ACTIVE_DIRECTORY),
`vcf-lab-vcenter-wld02.int.sentania.net` (VC), `vcf-lab-mgmt` (VC). Note the
local source is not in that list, which is itself a UI design constraint.

### 0.7 TLS

DEVEL presents a **self-signed certificate in its chain**; Python's default
context fails with `CERTIFICATE_VERIFY_FAILED`. Leaf SHA-256 fingerprint:

```
44363784e1aaca4a58f93310843929449fc0b149e25d6f8e23facc027891e67a
```

I disabled verification for recon only, in a throwaway script under `/tmp`
that is not committed. Section 3.3 says how the product handles this without
a global `verify=False`.

### 0.8 Version and pagination

```
GET /api/versions/current -> {"releaseName":"VCF Operations 9.0.2.0",
                              "major":2,"minor":2,"minorMinor":0,
                              "buildNumber":25137838}
```

Note `releaseName` says 9.0.2 while `major/minor` say 2.2. Record 006 already
warns that product version and API major/minor differ; here is the concrete
instance. **Never parse `releaseName` to select behavior.**

Pagination is `pageInfo: {totalCount, page, pageSize}` plus a `links` array
carrying `SELF` / `NEXT` / `RELATED` rels. `NEXT` is present even on a
single-page result, so **presence of `NEXT` does not mean more pages**; compare
`(page+1)*pageSize` against `totalCount` instead.

### 0.9 What I did not measure

- Anything on PROD. Deliberately untouched.
- Whether `POST /api/actions/{id}/query` (populate) is side-effect-free. That
  is record 007's blocking Q2 and it is a Phase 2 question; probing it means
  potentially mutating, so I did not.
- Concurrent acquires were **sequential-rapid (5 in 0.9 s), not truly
  parallel**. I did not establish an appliance-side session cap. My design
  below does not depend on there being one, but a peer who wants to attack my
  single-flight argument should attack it there.
- Report *run* endpoints. I listed `/reportdefinitions` and `/reports` (200),
  but running a report creates an artifact, so I did not.

---

## 1. Approach

### 1.1 The shape, in one paragraph

One Python package `src/vcf_ops_mcp/` in one container, one uvicorn process,
one Starlette parent app mounting three children: FastMCP's
`streamable_http_app()` at `/mcp`, the Jinja2 admin UI at `/admin`, and
`/healthz`. Underneath sit four layers with deliberately narrow seams: a
**store** layer (SQLite + the AES-GCM envelope), a **vcf** layer (one
`TargetClient` per registered target owning `/suite-api` URLs and the token),
a **dispatcher** (the single mandatory audited, authorized entry point every
tool passes through), and a **tools** layer of thin read-only handlers that
are structurally incapable of reaching the network except through a typed
domain adapter.

### 1.2 Files

```
src/vcf_ops_mcp/
  app.py                  Starlette parent, mounts, lifespan, /healthz
  config.py               env + path config, startup fail-closed checks
  store/
    schema.sql            versioned DDL, single source of truth
    db.py                 connection, migration runner, integrity checks
    crypto.py             AESGCM envelope, versioned keyring, AAD binding
    targets.py            target registry CRUD
    apikeys.py            mint / verify / revoke, constant-time compare
    audit.py              append-only audit writer
  vcf/
    client.py             TargetClient: token cache, single-flight re-auth, TLS
    errors.py             typed error hierarchy, 401 vs 403 vs 5xx vs transport
    projection.py         field projection sets + result caps
    domains/
      inventory.py        adapterkinds, resource kinds, resource query
      metrics.py          statkeys, stats query, supermetrics
      alerts.py           alerts, symptoms  (READ ONLY, no mutation verb)
      reports.py          report definitions, report list
  capability.py           the capability registry (section 4)
  dispatch.py             the audited, authorized dispatcher
  tools/
    registry.py           tool registration; refuses undispatched handlers
    targets_tools.py  inventory_tools.py  metrics_tools.py
    alerts_tools.py   reports_tools.py    skills_tools.py
  skills/
    catalog.py            immutable index load + validate at startup
    render.py             one canonical renderer, four exposures
  admin/
    routes.py  auth.py  csrf.py  templates/*.html
skills/                   content, per record 005
tests/
  fixtures/               sanitized synthetic contracts
  contract/               live DEVEL tests, opt-in, allowlisted host
```

### 1.3 The dispatcher, and why registration is what makes it mandatory

Record 001 requires every tool call to route through one mandatory audited
dispatcher, and record 002 rules out HTTP middleware as the audit boundary
because Streamable HTTP request count is not tool-call count. Both are right.
The open question those records leave is what *makes* it mandatory, because
"every handler calls the dispatcher" is a convention, and conventions are what
the fourth handler written at 11pm forgets.

I make it structural at **registration** time, not call time. Tool handlers are
never passed to FastMCP directly. They are declared as plain functions carrying
a `@tool(...)` decorator that records name, capability scope, projection set,
and argument model into a module-level registry, and does **not** register
anything with FastMCP. At startup, `registry.bind(mcp)` walks the registry and
registers, for each entry, a *generated* wrapper closure that calls
`dispatch(entry, ctx, args)`. The raw handler is never the thing FastMCP holds.

The consequence is the property I actually want: **a handler that forgets the
dispatcher is not an unaudited tool, it is a tool that does not exist.** It is
never registered, so it never appears in `tools/list` and cannot be called. The
failure mode of forgetting is invisibility, not silent unaudited execution.
A test asserts `set(registry) == set(mcp._tool_manager.list_tools())` so a
hand-registered side door fails CI.

`dispatch()` does, in order, per call:

1. Resolve key identity from the request-scoped `AccessToken` (record 002's
   `TokenVerifier`).
2. Resolve target, check the key's target allowlist.
3. Check the capability scope of this tool against the key's granted scopes
   intersected with global policy, **default deny**.
4. Check target posture (section 4).
5. Write an `attempt` audit record.
6. Run the handler with a deadline.
7. Write the terminal audit record (`ok` / `denied` / `error` / `timeout`).

### 1.4 `TargetClient` and the token lifecycle

One `TargetClient` instance per registered target, held in a process-level
registry keyed by `target_id`, built lazily and invalidated when the admin UI
edits that target. It owns an `httpx.AsyncClient` (httpx is already in the
`mcp` dependency graph per record 002's verified venv, so this is not a new
dependency) and this token state:

```python
self._token: str | None
self._expires_at: float | None      # epoch seconds, from `validity`
self._lock: asyncio.Lock
self._auth_generation: int          # monotonic
```

**Acquire path.** Before every request, if `self._token is None` or
`now > expires_at - 300` (a 5 minute skew margin against the measured 6 hour
TTL), acquire. The acquire itself is single-flight: the caller takes
`self._lock`, re-checks the token under the lock, and acquires only if it is
still stale. Concurrent callers block on the lock and then find a fresh token
rather than each acquiring.

**401 path, and the generation counter.** This is the part worth attacking.
A naive `if 401: async with lock: reacquire()` means N concurrent callers that
all 401 will serially acquire N tokens, because each takes the lock in turn and
each sees a token that is technically fresh but is the one *it* already knows
failed. The fix is a generation counter: each caller captures
`gen = self._auth_generation` **before** issuing its request. On a 401, it
takes the lock and re-checks `if self._auth_generation == gen`. Only the first
arrival matches, so only it re-acquires and bumps the generation; the others
find the generation moved, conclude someone else already fixed it, and simply
retry with the new token. **One re-acquire per 401 storm, exactly once, and
losers await rather than retry-storm.**

Retry is **once**. A second 401 after a fresh token is a credential or
permission problem, not an expiry problem, and it surfaces as an error. Record
006 already says "one reauthentication attempt after 401" and my measurement of
the 403 path (0.5) is why the trigger condition must be `== 401` and not
`in (401, 403)`.

Honestly stated, my measurements say this machinery buys **efficiency, not
correctness**: I measured that 5 rapid acquires all succeed, all stay valid,
and cost 0.9 s total, so the naive version would not have broken anything on
this appliance today. I still want the generation counter, because "the
appliance did not rate-limit us at 5" is not "the appliance will not rate-limit
us at 50", and the code is about fifteen lines. A peer who thinks that is
over-engineering has a fair argument and I would not fight hard for it.

**Shutdown.** `POST /auth/token/release` per target in the lifespan teardown.
I measured that release is per-token and does not disturb siblings, so this is
safe and is simple hygiene.

### 1.5 TLS, honestly

Per-target `verify_ssl` is not a boolean. It is a three-state column, because a
boolean is what forces the dishonest answer:

| Mode | Behavior |
| --- | --- |
| `system` | Default. Standard verification against system roots. |
| `pinned` | Verify against the stored SHA-256 leaf fingerprint for this target. |
| `insecure` | No verification. Requires an explicit admin confirmation and is loudly flagged in the UI and on every audit record for that target. |

DEVEL is self-signed (0.7), so the honest answer for our own lab is `pinned`,
not `insecure`. Registration flow: the operator enters the FQDN, the server
fetches the presented leaf, displays its fingerprint and subject, and the
operator confirms it. That is trust-on-first-use with a human in the loop, and
it degrades to a hard failure if the cert later changes, which is the property
`verify=False` throws away. httpx does not expose fingerprint pinning directly,
so this is implemented as a custom `ssl.SSLContext` with verification enabled
against an in-memory CA if the lab CA is available, and otherwise a post-
handshake fingerprint check on the peer cert. **I flag this as the piece of my
proposal most likely to need an implementation-time fallback**, since the exact
httpx hook may push me to a small transport subclass.

### 1.6 Target registry schema

```sql
-- schema_version tracked in a one-row `meta` table; migrations are
-- forward-only numbered scripts applied in a transaction.

CREATE TABLE targets (
  target_id       TEXT PRIMARY KEY,     -- uuid4
  name            TEXT NOT NULL UNIQUE,
  fqdn            TEXT NOT NULL UNIQUE,
  auth_source     TEXT,                 -- NULL = local
  username        TEXT NOT NULL,
  password_ct     BLOB NOT NULL,        -- AESGCM envelope
  password_nonce  BLOB NOT NULL,
  password_keyid  TEXT NOT NULL,
  tls_mode        TEXT NOT NULL DEFAULT 'system',   -- system|pinned|insecure
  tls_fingerprint TEXT,                 -- required when tls_mode='pinned'
  posture         TEXT NOT NULL DEFAULT 'read_only',-- read_only|actions_enabled
  is_prod         INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  CHECK (posture IN ('read_only','actions_enabled')),
  CHECK (NOT (is_prod = 1 AND posture = 'actions_enabled')),
  CHECK (tls_mode IN ('system','pinned','insecure')),
  CHECK (tls_mode <> 'pinned' OR tls_fingerprint IS NOT NULL)
);
```

The two `CHECK` constraints are the point. **The prod hard-block and the
read-only default are expressed in the schema, not only in Python.** A bug in
an admin route that tries to enable actions on a prod target fails at the
database with an `IntegrityError`, not at a forgotten `if`. That is one of the
three layers in section 4.

`is_prod` is set by matching the FQDN against a checked-in constant list that
includes `vcf-lab-operations.int.sentania.net`, evaluated at insert **and**
re-evaluated at every startup, so renaming a row cannot launder a prod
appliance into a devel one.

**AAD** binds each ciphertext per record 003's four-part rule:
`f"{schema_version}|{target_id}|password|{key_id}"`.

**Key-file absence or corruption.** Record 003 says fail closed and never
regenerate over existing ciphertext. Concretely, at startup:

| State | Behavior |
| --- | --- |
| No keyring, no ciphertext rows | Generate a keyring, log it loudly. First boot. |
| No keyring, ciphertext rows exist | **Refuse to start.** Exit non-zero with a message naming the expected keyring path. |
| Keyring present, wrong mode/owner | **Refuse to start.** |
| Keyring present, a row fails to decrypt | Start, but mark that target `unusable` and surface it in the UI. One bad row does not take the server down; it takes that target down. |
| Keyring present, *every* row fails | **Refuse to start.** This is a wrong-keyring situation, not a data situation. |

That last split is a judgement call I would defend: one undecryptable row is
plausibly corruption, all rows undecryptable is almost certainly the operator
mounting the wrong volume, and coming up "healthy" in that state is how a
restore gets silently half-completed.

### 1.7 Audit log

**Format:** newline-delimited JSON, one object per line, to
`/data/audit/audit-YYYYMMDD.jsonl`. Not SQLite. The audit log's requirements
are append-only, survivable, greppable by a human at 2am, and rotatable, and
NDJSON on a volume satisfies all four without holding a write lock that
competes with the credential store's transactions.

**Record:**

```json
{"ts":"2026-07-21T20:14:02.113Z","event":"tool_call","phase":"complete",
 "call_id":"01J...","key_id":"vok_pub_7f3a","target_id":"...",
 "tool":"query_resources","args_digest":"sha256:...","args_shape":{...},
 "status":"ok","duration_ms":412,"result_bytes":2124,"upstream_status":200}
```

`args_digest` is SHA-256 over a canonicalized (sorted-key, separator-normalized)
JSON serialization. `args_shape` carries key names and value *types* only, never
values, so an investigator can tell "somebody queried by resourceKind" from
"somebody queried by name" without the log becoming a data-exfiltration channel.

**Rotation:** daily by filename plus a size cap, with a retained-file count.
Written by the app, not logrotate, because the app is the only thing that knows
when it is between records.

**Does audit-write failure fail the tool call? Yes.** This is the question the
assignment asks and I want to answer it without hedging. The constitution says
no tool path ships without its audit write. If the audit write is best-effort,
then the guarantee is "audited unless the disk is full", and "the disk was full"
is an attractive state for an attacker to induce. So: the `attempt` record is
written **before** the handler runs, and if that write fails, the tool call is
refused with an error naming the audit subsystem.

The obvious objection is that this makes a full volume into a total outage. I
accept that and mitigate it rather than softening the rule:

- A startup check refuses to boot if the audit volume is unwritable, so this
  surfaces at deploy rather than mid-session.
- A background free-space check flips the server to a degraded state at a
  configurable low-water mark (default 100 MB), which fails calls *early* with
  a clear message and shows a red banner in the admin UI.
- `/healthz` reports audit-writability, so the container orchestrator sees it.
- Rotation and retention mean the normal steady state does not grow unbounded.

An outage that says "the audit volume is full" is a good outage. Silent
unaudited execution is not.

### 1.8 Skills

Straight implementation of record 005, no reinterpretation: immutable
`skills/<slug>/<semver>/SKILL.md`, a CI-generated `skills/index.yaml` validated
by exact regeneration, one catalog object loaded and digest-verified at startup,
and four exposures rendering from it (resource `skill://<slug>/<version>`, the
`current` alias, prompt `use_<slug>`, and the `list_skills` / `get_skill`
tools). `get_skill` serves only from the in-memory index and never touches a
path derived from an argument. `SKILLS_DEV_PATH` exists, defaults off, and
refuses to load if any registered target is `actions_enabled`.

Seed content is the three SPEC 4.2 skills. I would write the suite-api auth
walkthrough from section 0 of this document, which is now the most accurate
description of that appliance's auth behavior we have.

---

## 2. Risks

### 2.1 The Gate 1 credential scope is the top risk and it is not a code risk

Section 0.3. The delivered account sees 4 objects and zero VMs. If nobody acts,
Phase 1 ships correct and gates badly. **This is the thing I would spend my one
hour and one question on**, and the question is for lab-admin, not for the team:
*can the `vcf-ops-mcp` ReadOnly user's role scope be widened to `allowAllObjects`
on DEVEL?* Everything else in this proposal I can resolve by writing code and
measuring; that one I cannot.

Secondary consequence: our contract tests will assert against a 4-object world
today and a several-hundred-object world after the fix, so **contract tests must
not assert exact counts.** They assert shape, required-field presence, and
monotonic properties.

### 2.2 Registration-time dispatcher binding is clever, and clever is a risk

Section 1.3's property depends on nobody calling `mcp.tool()` directly. I assert
this is enforced by a test comparing the registry to FastMCP's tool manager, but
that test reaches into `mcp._tool_manager`, a private attribute of a
dependency I do not control. If `mcp` 1.29 renames it, my structural guarantee
degrades to a convention with a broken test, and a broken test in CI gets
skipped before it gets fixed. Mitigation is to pin `mcp` and treat that test's
breakage as a blocking upgrade task, but I want it named rather than discovered.

### 2.3 Fail-the-call-on-audit-failure will be argued against, and might be wrong

I argued it hard in 1.7 because I believe it, but the honest framing is that I
am trading availability for a guarantee, on a lab server whose failure mode is
"Scott's Claude Code session stops working". If a peer argues the low-water-mark
degradation is enough and the hard failure is theater, that is a real argument.
My defense is that the constitution's wording is unconditional and a team should
not quietly reinterpret an invariant into a best-effort; if we want it
best-effort, that is an escalation to Scott, not a code comment.

### 2.4 TLS fingerprint pinning may not have a clean httpx hook

Section 1.5. I am confident in the design and less confident in the twenty lines
that implement it. Fallback is a documented lab-CA bundle mounted into the
container, with `pinned` deferred, and I would rather discover that in week one
than promise it and slip.

### 2.5 `stats/query` payload size is the real Phase 1 blowup risk

137,808 bytes for one resource at `maxSamples=1` (0.4). Record 001 made field
projection a Phase 1 requirement based on `/resources` sizing, and the
projection sets are easy there because the shape is flat and stable. Metrics are
worse: the caller controls `statKey`, the response nests per-stat arrays, and
"project the fields" does not obviously apply. I do not have a finished answer.
My working plan is a mandatory server-side cap on `resourceId x statKey x
maxSamples` with an explicit refusal naming the cap, rather than truncation,
because silently truncated metric data is worse than no metric data. But I am
proposing a constraint here, not a solved design, and I would rather say that
than present it as settled.

### 2.6 My decomposition has a genuine seam problem at `dispatch.py`

Section 3 splits the client from the dispatcher from the store. `dispatch.py`
imports from all three, so whoever owns it is blocked on all three or writes
against interfaces that do not exist yet. I address it in section 3 by
sequencing interfaces first, but a peer proposing a different cut should aim
here, because this is where my cut is weakest.

### 2.7 Wrong-auth-source diagnosis is unsolvable at the API layer

Section 0.2: a wrong `authSource` and a wrong password return byte-identical
401s. The admin UI cannot tell the operator which one they got wrong. The best I
can do is prevent it: populate the auth-source dropdown from the target's own
unauthenticated `GET /api/auth/sources` (0.6) at registration time, plus an
explicit "Local users" option since local is not in that list. That converts a
free-text field into a picker and removes most of the failure mode, but an
operator who picks the wrong entry from a valid list still gets an unhelpful
401, and I cannot fix that.

### 2.8 Things I am simply unsure about

- Whether VCF Private AI Services tolerates our tool surface. Record 002 flagged
  it as the largest external risk local design cannot settle and assigned me the
  smoke test. It is still unsettled and Phase 1 is when it becomes testable.
- Whether `NEXT` link semantics (0.8) hold on every collection or only on
  `/resources`. I checked one endpoint and generalized. That is an inference.
- Whether the appliance rate-limits acquires above 5 concurrent (0.9).

---

## 3. Division-of-labor claim

### What I claim

**The `vcf/` layer: `TargetClient`, token lifecycle, TLS, the typed error
hierarchy, and the four read-only domain adapters.**

Why me, specifically, rather than as a general claim of competence: I have spent
this dispatch inside that appliance's actual behavior and the proposal above is
mostly a record of it. The four things that shape this layer are the alias
allowlist, the 6-hour TTL with independent tokens, the 401-versus-403 split with
its HTML-versus-JSON body inconsistency, and the fact that three of four read
families are POST. I measured all four today. Handing this piece to a resident
who would have to re-derive them means either re-running my recon or trusting my
table, and the second is how a subtly wrong constant gets into the layer
everything else sits on.

The secondary reason is continuity with what is already assigned to me. Record
006 defined `vcf/client.py`'s contract. Record 001 assigned me the catalog
fingerprint, record 007 generalized that to the per-family precondition
fingerprints and the revalidation adapter contract, and every one of those
fingerprints is computed over a response this layer parses. If someone else owns
the parsers, then in Phase 2 I own a fingerprint contract over field sets I do
not control, and record 007 already recorded the principle that splitting one
canonicalization rule across two residents is the wrong cut.

I additionally hold, from record 003, API-key mint/verify/revoke and the
constant-time comparison, and from records 002 and 007 the VCF Private AI
Services smoke test. I am not re-claiming those; I am noting they are mine and
that the smoke test in particular becomes actionable this round for the first
time.

### What I explicitly do not claim, and who should have it

**The store layer (`store/crypto.py`, the keyring, rotation, migrations) should
go to codex-worker, not to me.** Record 003 already assigned the envelope and
the rotation state machine to codex-worker on the grounds that I conceded its
four-part AAD binding was better than mine, and nothing this round changes that.
Section 1.6's schema is my proposal for the *shape*, and I would hand it to
codex-worker to own and revise rather than build it and hand over a fait
accompli. The keyring startup state table in 1.6 is the part I would most want
codex-worker to overrule me on if it disagrees, because it owns the failure
semantics of that file.

**The admin UI should go to agy-worker.** Record 004 settled the stack and the
hardening list (scrypt, per-session CSRF, session rotation, short idle lifetime,
recent-reauth before sensitive operations), so this is now careful
implementation of a specified surface with a lot of small correct-by-checklist
pieces, which record 007 already identified as agy-worker's stated strength when
it assigned it flat schema validation and the grantable-scope registry. The
grantable-scope registry is admin-UI-facing and I handed it away last round for
exactly that reason; putting the UI next to it keeps that pair together.

**The dispatcher itself I would rather share than own.** It is the seam I named
in 2.6 and it is the one file that must be right. My preference is that I write
`capability.py` and the posture-check chain (section 4 is my design and I should
own its enforcement), codex-worker writes the audit writer and its failure
semantics (it owns the store's durability story and 1.7's hard-failure rule is a
durability rule), and one of us assembles `dispatch.py` last against both
interfaces. If the orchestrator wants a single owner for a single choke point,
which is a defensible call, I would give it to codex-worker rather than take it,
because the audit-write-fails-the-call rule is the harder half and it should sit
with whoever owns durability.

**CI, container, and deploy I do not claim and have the weakest basis for.** I
read the lab-container-host contract this dispatch and I have not built against
the docker.int slot model. Whoever has actually shipped through `ai-log-depot`'s
pipeline should take it. If nobody has, it should be its own small slice rather
than a tail appended to someone's main piece, because a deploy job that slips is
what turns Gate 1 from a demo into a rescheduling.

---

## 4. Where read-only enforcement lives

Called out separately because the assignment names it fork 4 and because 0.4
makes the obvious answer unbuildable.

**It cannot be at the HTTP verb.** Three of four read families are POST.

**It cannot be only in the tool handler.** Phase 1 ships no action paths, so
there is nothing to put a check inside, which is precisely the risk the
assignment names: the choke point gets built later, in the wrong place.

**So it lives in a capability registry that exists in Phase 1 and is exercised
in Phase 1, even though every capability in it is currently read-only.**

`capability.py` declares:

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

Every tool declares exactly one capability at registration (1.3), and `dispatch`
refuses any tool whose capability is not declared. Three layers then apply:

1. **Schema.** `CHECK (NOT (is_prod = 1 AND posture = 'actions_enabled'))`
   (1.6). A prod target cannot be actions-enabled at rest, whatever any code
   path believes.
2. **Dispatcher.** `if entry.capability in MUTATING and target.posture !=
   'actions_enabled': refuse`. In Phase 1 `MUTATING` is empty so this never
   fires, and that is the point: **the branch exists, is on the mandatory path,
   and is covered by tests before there is anything for it to stop.** Adding an
   action capability in Phase 2 is adding a name to `MUTATING`, not building a
   gate.
3. **Grantable-scope derivation.** Per records 001, 003, and 007, the grantable
   scope set is derived at startup from registered adapters. No mutating adapter
   is registered in Phase 1, so no mutating scope exists, so the admin UI cannot
   render it and a key cannot hold it.

What makes it unbypassable is 1.3: a handler that does not go through
`dispatch` is not registered, and an unregistered tool is not callable. The
enforcement is not a check a handler can forget to call, it is the only route by
which a handler becomes reachable at all.

I also add a test that is deliberately annoying: **a test asserting
`MUTATING == frozenset()` for Phase 1.** Anyone adding a mutating capability
must delete that assertion, which is a visible, reviewable, greppable act in a
diff rather than a quiet addition.

---

## 5. Test strategy

Reconciling "verified against DEVEL" with "CI is hermetic, no appliance, no
secrets" is three tiers, not a compromise between two.

**Tier 1, unit, runs in CI, no network.** Crypto envelope round-trip and AAD
rejection (a ciphertext moved between target rows must fail to decrypt, which is
record 003's stated property and should be an actual test). Key derivation,
constant-time comparison, the dispatcher's authorization chain against a fake
store, projection, canonicalization, audit record shape.

**Tier 2, contract, runs in CI, no network, fixtures only.** A local ASGI mock
appliance serving sanitized fixtures, exercising the full `TargetClient` including
the 401 re-auth path (the mock returns 401 once, then 200, and the test asserts
**exactly one** acquire happened across N concurrent callers, which is the direct
test of 1.4's generation counter), the 403 path asserting **no** re-auth fires,
the HTML-error-body path, and pagination.

**Tier 3, live contract, never in CI, opt-in.** `pytest -m live` against DEVEL,
run by a resident on demand and by Scott at Gate 1. Guarded by record 006's rule
and I would make the guard mechanical: a session-scoped fixture that asserts the
configured host is on an allowlist that **does not contain the prod FQDN**, and
an httpx event hook that raises on any method outside `GET` and the two
documented token POSTs plus the enumerated read-POST paths. A live test that
tries to mutate fails as a test error, not as a mutation.

**On fixture scrubbing**, which the assignment correctly flags as the hard part.
I would not commit captured recon at all, even scrubbed, and this is a stronger
line than record 006's "sanitized synthetic contracts". My reasoning is that
scrubbing is a blacklist and blacklists lose: real captures carry resource names,
adapter instance names, IPs, UUIDs, and vCenter FQDNs in fields nobody thought to
list, and the failure is silent and permanent once committed.

Instead: a **recorder** run manually against DEVEL writes to a gitignored
`tests/fixtures/_capture/`. A **generator** reads a capture and emits a synthetic
fixture that preserves JSON structure, key sets, types, array cardinality, and
string format class (a UUID becomes a different well-formed UUID, an FQDN becomes
`host-3.example.invalid`) while carrying **no byte from the original values**.
Only the generated file is committed. Then a scanner runs in CI over
`tests/fixtures/` for the lab domain, RFC1918 addresses, the prod hostname, and
high-entropy strings, as a backstop and not as the primary control.

This is a whitelist, not a blacklist: the question changes from "did we remember
to scrub this field" to "which fields did we deliberately synthesize", and the
default for an unrecognized field is that it does not survive.

---

## 6. CI, container, deploy

Stated for completeness; per section 3 I am not claiming it.

Two workflows, fork-gated per the constitution. `ci.yml` on PR and push runs
lint, tiers 1 and 2, the fixture scanner, and the skills index exact-regeneration
check from record 005. `release.yml` on merge to `main` builds one image and
pushes `ghcr.io/sentania-labs/vcf-ops-mcp:<sha>` plus `:latest`, then a deploy
job to the docker.int slot over the slot deploy key in repo Actions secrets, per
the lab-container-host contract's multi-tenant slot model. Both on self-hosted
runners. CI never holds a VCF credential; there is nothing for it to hold, since
targets are configured post-deploy in the admin UI.

Three volumes, not two, because record 003's separation controls require the
keyring on a distinct mount from the database and excluded from the database's
backup artifact: `/data` (SQLite), `/keys` (keyring, 0600, distinct ownership),
`/audit` (NDJSON). Container runs non-root. Image tags are pinned, per the
contract's rule against `:latest` in compose.

---

## 7. Rough estimate

Order of magnitude, in dispatch-days across three doers working in parallel,
where a dispatch-day is one worker's productive session and not a calendar day.

| Slice | Estimate |
| --- | --- |
| `vcf/` layer, client, token lifecycle, TLS, 4 domain adapters | 3 to 4 |
| Store, crypto, keyring, migrations, target registry | 3 to 4 |
| Dispatcher, capability registry, audit writer | 2 |
| Admin UI, 5 forms, session auth, CSRF, hardening list | 3 to 4 |
| Skills surface, catalog, 4 exposures, 3 seed skills | 2 |
| Test infrastructure, mock appliance, generator, scanner | 2 to 3 |
| CI, container, deploy, slot handoff | 2, high variance |

Call it **15 to 21 dispatch-days of work, landing in roughly 6 to 8 elapsed
dispatch rounds** given three doers and the sequencing constraint that interfaces
must land before `dispatch.py` assembles.

**What I am most likely wrong about, in order:**

1. **The deploy slice.** It has the widest variance and the least team
   experience, it depends on a lab-admin handoff outside our control, and record
   004 already noted the fleet-caddy slot facts did not exist when it was
   written. If any single item doubles, it is this one.
2. **The metrics projection design (2.5).** I have a constraint, not a solution.
   If capping turns out to be unusable in practice and we need real response
   shaping for `stats/query`, that is a whole extra slice that appears in nobody's
   estimate right now.
3. **TLS pinning (2.4).** Small in the estimate, and the kind of small thing that
   eats a day when the library does not cooperate.
4. **I am probably underestimating the admin UI.** Record 004's hardening list is
   nine distinct requirements including recent-reauth, which needs its own state
   and its own tests, and "five simple forms" is the classic thing that is not.

I am *not* worried about the `vcf/` layer estimate. That is the slice I measured,
and measured work estimates well.

---

## 8. Flagged concerns about settled records

Per the instruction to flag rather than design around. I am not relitigating any
of these and my proposal implements every record as written.

**Record 001's resource sizing is now unrepresentative.** The `508 resources /
1,097,361 bytes / 92% projection reduction` figures were measured with a wider
credential than the one we were delivered. The *conclusion* (projection is a
Phase 1 requirement) is untouched and I fully support it. The *numbers* should
not be cited as our expected payload profile until 2.1 is resolved. This is a
factual note, not a disagreement.

**Record 006 says "send `OpsToken`, not the legacy alias", and I measured that
both work.** The record's instruction is correct and I follow it. I flag only
that the record's phrasing implies the alias might not work, and a future
resident debugging against vcf-content-factory's `client.py` (which sends
`vRealizeOpsToken`) may waste time deciding the reference client is broken. It is
not. Worth a one-line amendment to 006 if the orchestrator agrees, and not worth
a round if it does not.

No standing dissent.
