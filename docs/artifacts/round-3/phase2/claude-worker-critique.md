---
source-ref: 48b68d0746779955358953103e6838c56f5ae174
source-commit: 48b68d0746779955358953103e6838c56f5ae174
source-blob: 45a35fc5fd11d0a44da8a8089e3d00e5ab8258c5
source-path: docs/proposals/p2-critique-claude.md
worker: claude-worker
round: round-3
phase: phase2
captured: 2026-07-26
---

# Phase 2 critique, claude-worker

- **Round:** vcf-ops-mcp Phase 1, adversarial critique
- **Dispatch:** `vom-p1-crit-claude-20260721-200421`
- **Branch:** `claude/p1-critique`
- **Author:** claude-worker
- **Critiquing:** `docs/proposals/codex-worker-phase1-build.md` (`ae23955`) and
  `docs/proposals/agy-worker-phase1-build.md` (`f136b2a`). Not my own
  (`docs/proposals/p1-build-claude.md`, `bfc2382`).

---

## 0. New measurements taken this round

Everything here I ran today against
`vcf-lab-operations-devel.int.sentania.net` with the delivered ReadOnly
service account. Nothing against PROD. No token or password value appears
here or in any committed file. These four measurements are what most of the
critique below rests on, and two of them disprove a claim in my own proposal.

### 0.1 Every Phase 1 read family has a working GET form. My "unbuildable" claim was wrong.

My proposal section 0.4 said verb-based read-only enforcement is unbuildable
because three of four read families are POST. That was an over-generalization
from "the `/query` endpoints are POST" to "reads are POST". Measured:

| Call | Result |
| --- | --- |
| `GET /api/resources?resourceKind=VirtualMachine&pageSize=1` | 200 |
| `GET /api/resources?regex=.*Cont.*` | 200, filter honored |
| `GET /api/resources/{id}/statkeys` | 200 |
| `GET /api/resources/{id}/stats/latest` | 200, 2650 B |
| `GET /api/resources/stats/latest?resourceId={id}` | 200, identical body |
| `GET /api/resources/stats?resourceId={id}&statKey=...&begin=&end=` | 200 |

So codex-worker's GET-only base transport is **buildable for the whole Phase 1
surface**, and I was factually wrong to say otherwise. Full concession in
section 3.

### 0.2 The GET URI ceiling is not the limiting factor either

I expected to bound GET-only by URI length, since a metrics tool over N
resources must repeat `resourceId=` N times. It does not bind at any Phase 1
scale:

| N resourceIds on `GET /api/resources/stats/latest` | URI length | Result |
| --- | --- | --- |
| 50 | 2,427 | 200 |
| 200 | 9,627 | 200 |
| 500 | 24,027 | **200** |

24 KB of query string is accepted. The `POST .../stats/latest/query` form at
300 ids returns a byte-identical body. So the POST query endpoints buy
expressiveness we do not currently need, and the GET-only argument does not
fail on URI limits.

### 0.3 Unknown GET query parameters are silently ignored and return the unfiltered collection

This is the finding that actually matters, and it cuts against GET-first
designs rather than for them.

| Request | `pageInfo.totalCount` |
| --- | --- |
| `GET /api/resources?pageSize=1` (no filter) | 4 |
| `GET /api/resources?resourceId=<real uuid>` | **1** (correct param) |
| `GET /api/resources?identifier=<real uuid>` | **4** (silently ignored) |
| `GET /api/resources?identifier=<bogus uuid>` | **4** (silently ignored) |
| `GET /api/resources?bogusParam=zzz` | **4** (silently ignored) |
| `GET /api/resources?resourceKind=NoSuchKind` | 0 (recognized, honored) |

A wrong or misspelled filter parameter does not 400. It returns the entire
collection. `identifier` is a plausible wrong guess for `resourceId`, since
`identifier` is the field name in the response body, and it fails open.

Consequence: pushing all filtering into query strings, which is what a
GET-only transport forces, converts a typo into a full-collection return.
That is exactly record 001's 274k-token response, arrived at by a one-word
mistake with no error anywhere. Both peers' designs are exposed to this and
neither anticipated it.

### 0.4 `GET /api/reports` on DEVEL returns `totalCount: 0`

There are no completed report instances on the DEVEL appliance. Load-bearing
for the critique of codex's report scoping (section 1.8).

Also confirmed, since codex asserted the collection envelope keys and I wanted
to check rather than accept them: `adapter-kind`, `resourceList`,
`superMetrics`, `alerts`, `symptom` (singular, as codex reported),
`reportDefinitions`, `reports`. **Codex's envelope table is correct in every
entry, including the singular `symptom`, which is the sort of thing that is
usually wrong.** Tested and could not break it.

---

## 1. codex-worker

### 1.1 Steelman

The build is cut into three slices around *interfaces* rather than features,
because a per-family vertical cut would force all three doers to edit app
registration, migrations, authorization, and audit plumbing, producing both
merge collisions and three subtly divergent enforcement paths. A single short
`contracts.py` commit lands first and is the only planned serialization point.

Enforcement is structural in two independent places. The transport exposes
only `request_read()`, which refuses every upstream method except GET plus two
named token paths; `request_mutation()` is private to a future transport that
requires a typed plan token and rechecks posture immediately before I/O. Tool
code cannot name a method. Separately, `ToolRegistry.register()` refuses any
tool lacking a capability, scope, target policy, digest policy, projection and
audited handler, and FastMCP handlers are generated only from the sealed
registry, so there is no route by which a domain function becomes a callable
tool without passing the gate. Because no Phase 1 capability claims a mutation
scope, the derived grantable-scope registry cannot even render one in the
admin UI.

Audit is a durable `started` row committed before the adapter is invoked and
finalized after, in a separate SQLite database on its own volume, with HMAC
argument digests keyed separately from the encryption keys so low-entropy
arguments cannot be enumerated offline. Any write, sync, integrity or space
failure makes MCP readiness false while health stays up for diagnosis.

Report *run* is classified as mutation by record 007, so Phase 1 ships no run
path, and codex flags this as a live tension with SPEC rather than resolving it
unilaterally.

That is a coherent proposal and the strongest of the three on the persistence
and policy half.

### 1.2 The GET-only predicate is already a path allowlist, so "GET" does no independent work

Codex's own rule is "every upstream method except GET **plus the narrowly named
token acquire and release paths**". Those two carve-outs are POSTs that create
and destroy server-side session state. They are mutations, whitelisted by name.

So the enforced predicate is not "method == GET". It is "(method, path) is in a
hardcoded allowlist". Once that is admitted, the verb is carrying no weight of
its own: the security property comes entirely from the allowlist, and "GET" is
a naming convention for the common case. This matters because codex sells the
verb rule as the structural guarantee and a registry test proving "declared
upstream verbs are GET" as the proof. That test proves the convention, not the
property. A Phase 2 action that happens to be shaped as a GET, and VCF Ops has
GET-shaped operations with side effects in its report and task surfaces, passes
the verb test while being a mutation.

**What breaks and when:** the first Phase 2 adapter whose upstream call is a
GET. The registry test stays green, `request_read()` accepts it, and the
mutation gate is bypassed without anyone editing the gate. The failure is
silent because the guard was never keyed on the thing that matters.

### 1.3 GET-only over-blocks in a way that is now measurably dangerous

Section 0.3. Forgoing `POST /api/resources/query` means every filter is a query
parameter, and this appliance silently ignores unrecognized query parameters
and returns the unfiltered collection. Codex's design has projection and page
caps, which bound the *bytes* per page, but not the *scope*: a tool asked for
"the VMs on adapter X" that silently returns every object the key can see is
returning objects the caller did not ask for, correctly projected and correctly
paginated. Projection does not save you here because nothing is malformed.

**Concretely:** codex's inventory adapter builds `?identifier=<uuid>` instead of
`?resourceId=<uuid>` and every fixture test passes (the fixture returns what the
fixture author expected), while against a real appliance the tool returns the
whole inventory on every call. Fixture-backed contract tests cannot catch this
class, because the mock replies to the URL it was given.

The fix is cheap and belongs in whatever we adopt: **a per-tool allowlist of
permitted query parameter names, asserted against the appliance at least once
in the live tier.** I would rather codex added that than dropped GET-only.

### 1.4 Withholding a successful result on audit-finalization failure buys nothing

"If finalization fails after an upstream read, the client gets
`audit_unavailable` ... and the result is not returned."

Test this against the threat model. The adapter has already run. The read
already happened at the appliance. The durable `started` row already records
who called what, against which target, with which argument digest. The only
thing the finalization row adds is the outcome. Withholding the response does
not un-read the data, does not reduce what the caller learned (they can
re-call), and does not improve the audit record by one byte. It converts a
transient audit-store problem into data loss for the user while leaving the
security posture exactly where it was.

I hold the *opposite* half of this rule and I want to be precise that I am not
just defending my own: I argue the **attempt** write must be fatal, because
before it there is genuinely no record and refusing costs nothing. Codex agrees
on that. Where codex goes further, to the finalization, the cost becomes real
and the benefit is zero. Codex is right about the ordering and wrong about the
tail.

**Recommendation:** on finalization failure, return the result, mark the call
`unfinalized` in memory, and surface a reconciliation count in `/healthz` and
the admin UI. The `started` row is the audit; the finalization is metadata.

### 1.5 An audit store you can `DELETE FROM` is not append-only

Codex puts audit in SQLite with monthly archive rotation: back up to a
read-only archive via the SQLite backup API, integrity check, then remove rows
from the live file. Archives are never auto-deleted, which is the right
instinct.

Two problems. First, the invariant we are protecting is durability of the
record against an actor who wants it gone, and a SQL table is the one storage
format where "make selected records disappear without leaving a hole" is a
single statement. NDJSON files where deletion means truncating or unlinking a
whole dated file are harder to edit selectively and trivially verifiable by
size and line count. Second, the rotation procedure itself (backup, verify,
delete) has a crash window in which rows exist in two places or neither, and
codex's own risk list concedes it "adds failure modes around backup
verification and row cutover". Codex then offers the reduced scope of no
automatic rotation, which I think is correct and should be the *primary* plan
rather than the fallback.

I concede the reason codex chose SQLite (one transactional model, admin queries,
atomic revocation) is real, and that my NDJSON does not give the admin UI a
queryable audit view without a reader. That is a genuine cost of my position
and codex is right that it exists.

### 1.6 `contracts.py` is not a one-time serialization point

The claim is that a short common-contract commit lands first and then three
slices proceed without editing the same files. I do not believe this survives
week one, for a specific reason: `ToolRegistry.register()` lives in slice 1 and
requires each adapter to declare capability, key scope, allowed verbs, result
cap and projection version. Adapters live in slice 2.

Every time slice 2 discovers a declaration field it needs, and it will, because
the metrics family needs a per-call sample cap that inventory does not (my
proposal 2.5, and codex's own `stats` handling implies the same), the registry
signature in slice 1 changes, slice 1's registry tests change, and slice 3's
`app.py` generation may change. That is a three-way edit on the hottest file in
the tree, recurring, not once.

This is the same weakness I named in my own proposal 2.6 about `dispatch.py`.
Codex has renamed the seam, not removed it. Naming it "the only planned
serialization point" is the part I object to, because a plan that budgets one
barrier and gets five is how a parallel round turns serial in practice.

**Mitigation I would accept:** make the registration record an open, versioned
mapping with a small required core rather than a fixed signature, so adding a
per-family field is an additive change in the adapter plus a reader in the
dispatcher, not a signature break.

### 1.7 Slice 3 is oversized and its own estimate contradicts its own file list

Slice 3 owns `app.py`, `mcp_server.py`, `admin/`, `templates/`, `skills/`,
`Dockerfile`, `compose.yaml` and the build-deploy workflow. Codex estimates it
at 4 to 6 resident-days and concedes it is "uneven" and "the most likely
schedule tail".

Price the contents. Record 004's admin hardening list alone is nine
requirements including scrypt, per-session CSRF, session rotation, short idle
lifetime and recent-reauth before sensitive operations, and recent-reauth needs
its own state and its own tests. Record 005's skills surface is a catalog, a
digest check and four distinct exposures. CI plus container plus a first
deploy through the docker.int slot is high-variance work nobody on this team
has done. That is not 4 to 6 days, it is closer to 8 to 12, and it is the slice
Gate 1 depends on most directly, because Gate 1 is Scott connecting a client
through fleet-caddy to a deployed container.

**What breaks:** slice 1 and slice 2 finish, slice 3 is half done, and Gate 1
slips on deploy rather than on the server. Codex's mitigation ("ship admin and
MCP first while CI support follows") makes it worse, because CI and deploy are
the long pole and deferring the long pole is how a tail becomes the schedule.

The three slices should be rebalanced by moving skills, which is
self-contained and has no dependency on admin session state, out of slice 3.

### 1.8 The Phase 1 reports family delivers almost nothing, and DEVEL cannot demo it

Codex correctly drops report run per record 007, leaving Phase 1 with report
definition listing, completed-report listing and metadata, and download of an
existing report. Measured today: `GET /api/reports` on DEVEL returns
`totalCount: 0`. There are no completed reports.

So of the three surviving report capabilities, one works (definitions), one
returns an empty list, and one has nothing to operate on. Codex's own risk list
says "Gate 1 should prove a small real PDF download or narrow the tool to
metadata", and the measurement says Gate 1 **cannot** prove that today without
someone first running a report on DEVEL, which is a mutation nobody is
authorized to perform in Phase 1.

This is not an argument to re-open record 007. It is an argument that the
reports family should be scoped in Phase 1 to definitions plus completed-report
listing, explicitly documented as untestable end-to-end until Phase 2, so that
nobody budgets download work whose acceptance test cannot run.

### 1.9 Codex took a measurement and did not read it

Codex reports "`GET /api/resources` returned 200" and records the envelope key
`resourceList`. That same response body contains `pageInfo.totalCount: 4`, and
the four objects are `Universe`, `Container`, `Entire Enterprise Applications`
and one `VMWARE_INFRA_MANAGEMENT_INSTANCE`. Zero VMs, zero hosts, zero
datastores. The delivered service account's role has `allowAllObjects: false`
on a narrow scope.

Codex's proposal treats reachability as the finding and does not mention that
the inventory the whole read plane exists to serve is not visible to our
credential. Neither does agy's. This is the Gate 1 blocker from my proposal 0.3
and it survives contact with two peers who ran the same request and did not
look at the count. I raise it here not to score a point but because it is the
one item that needs a lab-admin round trip started today, and a critique round
is the last cheap moment to notice.

### 1.10 Points I tested and could not break

- The collection envelope key table (0.4), including singular `symptom`. Correct
  in all seven entries.
- The single-flight token design. Codex's generation-snapshot scheme is
  functionally identical to mine, and I could not construct a race in it: the
  pre-request snapshot plus compare-under-lock admits exactly one reacquire per
  storm, losers reuse the winner's token, retry is exactly once, and a second
  401 is typed rather than looped. My measurements (tokens are independent, no
  sibling invalidation, 6 hour TTL) mean the failure mode of even getting this
  wrong is waste, not corruption.
- HMAC-keyed argument digests with purpose-separated keys. I tried to argue this
  was over-engineering and could not. See 3.2.
- Refusing downgrades and refusing old-key removal while referenced. Correct.

---

## 2. agy-worker

### 2.1 Steelman

Keep the module count small and the layering obvious: a Starlette parent in
`server.py` mounting FastMCP, `/admin` and `/healthz`; one `client.py` holding
base URL, auth source, verify-SSL and token lifecycle; a `tools/` directory per
family; one `store.py` for the SQLite registry and the record 003 envelope; one
`audit.py`. Two tables, `targets` and `credentials`, split so credential
material is isolated from operational metadata.

Put read-only enforcement at the lowest possible layer, inside
`VCFOpsClient._request()`, on the theory that the deepest choke point is the
hardest to route around: even a developer who wrongly registers an action tool
finds the HTTP client refusing the method. Fail closed hard on keyring problems,
refusing to bind the port at all rather than starting degraded. Per-target
`verify_ssl` passed to that target's own `httpx.AsyncClient` so a self-signed
lab cert never becomes a process-global disable. Capture sanitized fixtures once
and replay them in CI through `httpx.MockTransport`, which keeps CI hermetic
while testing parsing against real response shapes. Take the `ai-log-depot`
CI pattern as-is rather than inventing one.

The instinct throughout is to prefer the smallest thing that satisfies the
constraint, and on the TLS point (per-target client, never a global disable) and
the `MockTransport` choice that instinct produces the right answer with less
machinery than either codex or I proposed.

### 2.2 The read-only choke point cannot authenticate

"The client strictly refuses any HTTP method other than `GET`" inside
`VCFOpsClient._request()`. Token acquisition is `POST
/suite-api/api/auth/token/acquire`, and the proposal says so explicitly two
paragraphs earlier.

So one of two things is true. Either acquire goes through `_request()`, in which
case the client refuses its own authentication and the server cannot make a
single successful call, or acquire bypasses `_request()`, in which case there is
already a code path in this class that reaches the network without passing the
guard. Agy does not carve out the exception (codex does, explicitly), so the
proposal as written is the first case, and the design does not boot.

Once you patch it into the second case, the claim "this makes the gate
unbypassable" is gone: the class contains a demonstrated bypass, written by the
same author, on day one. The next person who needs a POST for a legitimate
reason (say `POST /api/resources/query`, which is the natural way to filter, or
`POST /auth/token/release` at shutdown, which agy does not mention) follows the
precedent that already exists in the file.

**What breaks and when:** immediately, at first boot, and then structurally
forever after the obvious patch.

### 2.3 There is no projection layer, and record 001 made it a Phase 1 requirement

Search agy's proposal for response shaping. There is none: no projection, no
field selection, no page caps, no result-size caps, no mention of the HATEOAS
`links` share. `tools/` is described as "static tool registrations" and the
client as holding "base URL, auth source, verify-SSL and token lifecycle".

Record 001 made field projection a Phase 1 requirement on measured sizing. My
own measurement puts `POST /api/resources/stats/query` at 137,808 bytes for a
**single** resource at `maxSamples=1`, and section 0.3 above shows a
mistyped filter returns the whole collection. A metrics tool with no cap and no
projection returns that to an MCP client, which is where the 274k-token figure
in record 001 came from.

This is not a design disagreement I am picking. It is an accepted requirement
that is absent from the proposal, and its absence is why the estimate in 2.7 is
what it is.

### 2.4 The `credentials` schema makes key rotation unimplementable

```
credentials: target_id (FK), username, encrypted_password, nonce, schema_version
```

There is no key ID column. Record 003 specifies a versioned keyring with one
active key and decrypt-only old keys, and a four-part AAD binding that includes
the key ID. Without a per-row key ID:

- You cannot tell which key encrypted a given row, so with more than one key in
  the keyring you must trial-decrypt, and rotation cannot be resumable or even
  auditable.
- You cannot reconstruct the AAD, because the key ID is one of its four parts.
  So either the AAD is not what record 003 specifies, or the rows cannot be
  decrypted at all.

Agy claims this exact slice as its own on the strength of "parsing requirements
into concrete database schemas", and the concrete schema drops the field the
requirement's central mechanism depends on. Separately, `username` is stored in
plaintext beside the encrypted password; codex encrypts both. A username is not
a secret in the way a password is, but it is lab-identifying material sitting in
a database whose whole purpose is to not leak lab-identifying material.

### 2.5 Fail-closed on keyring absence bricks the first boot

"If the keyring file is absent, unreadable, or corrupted at startup, the server
fails closed immediately. It refuses to bind the port."

Absent is the state of every first deployment. With no initialization path, the
container never starts, and the operator's only recourse is to generate a
keyring by hand outside the app, in the exact format the app expects, which is
both undocumented at that point and the most error-prone possible way to create
key material.

Codex handles this correctly (absence with an empty database permits one
explicit atomic initialization path; absence with ciphertext present is fatal).
My proposal has the same split plus a case for partial decrypt failure. Agy's
undifferentiated rule is the right instinct applied without the case analysis,
and the failure lands on the very first deploy.

### 2.6 The audit design violates the invariant it is written to satisfy, twice

"Before the tool executes, the dispatcher verifies the volume is writable. When
the tool completes, it appends the JSON line."

**First:** a writability *check* is not a *write*. Between the check and the
append the volume can fill (the tool call itself may be what fills it, if the
audit line is large or another writer is active). That is a textbook TOCTOU, and
the mitigation is trivially available: write the attempt record instead of
checking for the ability to write one. Codex and I both do this.

**Second, and worse:** the only record is written on completion. If the process
is killed, the container is restarted, or the tool raises in a way that escapes
the handler, between the upstream read and the append, the call happened, data
was read from the appliance, and **no audit record exists at all**. The
constitution's rule is that no tool path ships without its audit write, and this
design has a window in which a completed read leaves zero trace. Agy's own
framing ("failing the tool call to satisfy the invariant") shows the invariant
was understood; the ordering silently defeats it.

### 2.7 Host logrotate cannot rotate this file, and the failure compounds with 2.6

"File rotation is handled by the container host (e.g. logrotate on docker.int),
not the application."

Three things wrong. First, logrotate on the host is not configured for arbitrary
container bind-mount paths, so in practice nothing rotates this file unless
someone writes and deploys a logrotate fragment, which is a deploy artifact
absent from the proposal. Second, if it *is* configured, default logrotate
renames the file, and a process holding an open descriptor keeps appending to
the renamed inode; every audit record after the first rotation goes to a file
nobody is reading, until the app is restarted. Avoiding this needs `copytruncate`
(which loses records written during the copy) or a signal-driven reopen in the
app, which is the application involvement the proposal declined. Third, this is
the audit log, and rotating it from outside the app means the rotation is
performed by a component that has no idea whether it is between records.

Now compound with 2.6: nothing rotates, the volume fills, and agy's own listed
risk (a disk-space issue cascading into complete MCP outage) fires. Agy names
that risk and then chooses the rotation design that guarantees it arrives.

### 2.8 Fixture scrubbing is named as a risk and then not designed against

"A developer runs a script against DEVEL ... sanitizes the response payloads
(scrubbing hostnames, tokens, and passwords)". The risk section then says this
"carries a high risk of leaking a token or password if the script misses a
header or a deeply nested JSON field".

That is a correct diagnosis with no treatment. Scrubbing is a blacklist, and a
blacklist over live VCF Ops payloads loses: resource names, adapter instance
names, vCenter FQDNs, IPs, UUIDs and description fields carry lab identity in
places nobody enumerates in advance, and the failure is silent and permanent
once it is in git history, which the constitution explicitly forbids
force-cleaning. "99% right" is the failure mode, not the success mode.

Codex's version is materially better and I will say so: allowlist projection to
explicitly permitted fields *before* replacement, deterministic synthetic
substitution, then a byte-level scan as a backstop, with raw captures confined
to a 0700 directory outside the repo. That is close to the whole-value synthesis
I proposed and I would take it. Agy's is the version the constitution's rule
exists to prevent.

### 2.9 The estimate is wrong by roughly a factor of four

"Approximately 3 to 4 days of calendar time", with "the core target registry and
read-only tools are straightforward (1 to 2 days)".

Codex says 12 to 18 resident-days, 5 to 7 elapsed. I said 15 to 21
dispatch-days, 6 to 8 rounds. Agy is not proposing a smaller scope that
justifies a smaller number; it is proposing the same scope (registry, crypto,
client, tools, admin UI with record 004's nine hardening requirements, skills,
CI, container, deploy) and pricing it at a fifth.

Two specific places the number cannot be right. The admin UI in record 004 is
scrypt, per-session CSRF, session rotation, idle lifetime and recent-reauth,
which is not a day. CI plus container plus a first deploy through a docker.int
slot, which agy's own risk section does not price at all, is high-variance work
this team has not done. Calling the registry and tools "straightforward (1 to 2
days)" while omitting projection, caps and pagination (2.3) is how the number
got there: the estimate is consistent with the proposal, and the proposal is
missing the requirements.

An unchallenged estimate becomes a schedule, so: **3 to 4 days is not credible
and should not be entered into the plan.** The credible band is codex's.

### 2.10 `vRealizeOpsToken` for consistency with the reference client

Agy reasons toward sending `vRealizeOpsToken` because vcf-content-factory's
`client.py` does. Record 006 selects `OpsToken` as the canonical 9.x form and we
all measured both returning 200. Consistency with a reference implementation we
are not shipping is not a reason to send the legacy alias from the client we
are. Send `OpsToken`, and note the alias in a comment so the next reader
debugging against `client.py` does not think one of them is broken. One
sentence, as instructed, and it is the only thing here that is purely a
preference rather than a defect.

### 2.11 Two doers have claimed the same slice

Agy claims the target registry and credential store. Codex claims the policy and
persistence spine, which contains the target registry and credential store.
Record 003 already assigned the envelope and rotation state machine to
codex-worker. Meanwhile the admin UI, skills and CI are claimed by nobody except
as the tail of codex's oversized slice 3, and agy's proposal is the only one of
the three that spells out the `ai-log-depot` CI pattern concretely.

This is an orchestrator decision, not mine, but the collision is real and the
gap is real, and my recommendation is in section 4.

### 2.12 Points I tested and could not break

- **Per-target `verify_ssl` on that target's own `httpx.AsyncClient`.** I tried
  to find a leak where one target's unverified context affects another and could
  not: httpx clients hold independent SSL contexts, and agy explicitly avoids
  process-global disabling. This is correct and it is the same conclusion codex
  reached. My own three-state pinning proposal is more secure in principle and I
  flagged it as the piece most likely to lack a clean httpx hook; agy's simpler
  version definitely works.
- **`httpx.MockTransport` for the fixture tier.** I proposed a local ASGI mock
  appliance. `MockTransport` is less machinery for the same coverage of the
  client's parsing paths. I could not name a Phase 1 test my ASGI app supports
  and `MockTransport` does not. Agy is right and I am wrong on this one.
- **Agy's one-hour question** (FastMCP context injection from ASGI middleware
  into tool handlers). I could not dismiss it. See 3.5.

---

## 3. Concessions

### 3.1 My "verb-based enforcement is unbuildable" claim was false

Section 0.1. I measured that the `/query` endpoints are POST and concluded
reads are POST. Every Phase 1 read family has a working GET form:
`GET /api/resources?resourceKind=`, `GET /api/resources/{id}/statkeys`,
`GET /api/resources/{id}/stats/latest`. And section 0.2 shows the URI ceiling
does not bind at 500 ids. Codex's GET-only transport is buildable and I said it
was not. That was the load-bearing claim of my proposal's section 4 and it is
wrong as stated.

What survives is narrower and I want to be honest about how much narrower: the
verb is the wrong *predicate* (1.2), not an impossible one.

### 3.2 Codex's HMAC argument digest beats my SHA-256

I specified `args_digest` as SHA-256 over canonicalized JSON. Phase 1 arguments
are low-entropy: a resource kind from a list of 21 adapter kinds, a target ID, a
stat key from an enumerable set. Anyone holding the audit log can enumerate the
space offline and recover the arguments, which defeats the point of digesting
them instead of storing them. HMAC with a purpose-separated key removes that.
I tried to argue it was over-engineering for a lab and could not. Adopt it.

### 3.3 Codex's length-prefixed AAD encoding beats my delimiter join

I wrote the AAD as `f"{schema_version}|{target_id}|password|{key_id}"`. Codex
specifies a length-prefixed encoding of the same four parts specifically to
avoid delimiter ambiguity. My version is safe only as long as no component can
contain a `|`, which is a property of today's values rather than of the
encoding. Codex's is unconditionally unambiguous. Adopt it.

### 3.4 Codex found a contract tension I did not see

SPEC names report `list/run/download` in the MVP; record 007 classifies report
run as mutation; Phase 1 is read-only. My proposal listed a `reports.py` adapter
for "report definitions, report list" and never noticed the conflict, which
means I had silently resolved it in passing. Codex surfaced it as a question for
the orchestrator instead. That is the better behavior and I missed it. My
measurement in 0.4 adds to codex's case rather than subtracting from it.

Codex's schema also carries an optimistic `revision` column and explicit FQDN
normalization (lowercase, trailing dot, reject URLs, ports and embedded
credentials) that my schema lacks. Both are right and both are things I should
have had.

### 3.5 I assumed the mechanism agy correctly worried about

My dispatcher's step 1 is "resolve key identity from the request-scoped
`AccessToken`", stated as though it were a given. Agy's one-hour question is
exactly whether identity survives the trip from ASGI middleware into a FastMCP
tool handler, and notes FastMCP context variables are tricky to wire from
middleware. My design depends completely on that working and I did not verify
it. If it does not work as assumed, every audit record and every authorization
check in my proposal is built on an identity that is not actually available at
the point of use. Agy is right to make it the first question.

### 3.6 Agy is right on two design points against me

`httpx.MockTransport` over my ASGI mock appliance (2.12), and per-target
`verify_ssl` as a plain boolean being sufficient, where my three-state
`system`/`pinned`/`insecure` design is better in principle but is the piece I
myself flagged as most likely to lack a clean httpx hook. If the pinning hook
resists on the first day, agy's version is the answer and I should not spend a
day proving otherwise.

---

## 4. What I now think the team should do

This differs from my own proposal in three places and I have marked them.

**1. Enforcement is a frozen (method, path, parameter) allowlist declared at
registration, not a verb rule and not only a capability check.** [Changed from
my proposal.] Codex is right that the transport must be structurally incapable
of issuing an ungated call, and I was wrong that a transport-level guard cannot
work. Codex is wrong that the guard is the verb: its own token carve-out proves
the real rule is a path allowlist (1.2). Merge them: each tool declares its
capability, its upstream method, its path template, **and its permitted query
parameter names**; the registry freezes the union; the transport refuses any
call outside the frozen set; the dispatcher checks capability and posture. The
parameter allowlist is the new piece and it is not optional, because section 0.3
shows an unrecognized parameter returns the unfiltered collection with a 200.
Keep my registration-time binding (an unregistered handler is not a tool that
exists) as the reason a handler cannot skip the path, and keep codex's empty
`MUTATING` set with a test asserting it is empty.

**2. Audit: attempt-write-before, fatal; finalization, non-fatal.** [Changed
from my proposal.] I argued in my 1.7 that audit failure fails the call, full
stop, and I still hold that for the attempt record: before it there is no
record, and refusing costs nothing. Codex extends it to finalization and
withholds an already-computed result, which costs the user their answer and buys
nothing (1.4). Adopt codex's ordering and HMAC digests (3.2), adopt my
attempt-is-fatal rule, and reject the finalization withholding. That answers the
orchestrator's question 3 directly: **the outage is the honest price for the
attempt write and is not the honest price for the finalization write.** Start
with no automatic rotation plus an early free-space refusal, which is codex's
own fallback and should be the plan (1.5).

**3. Fixtures: allowlist projection, then whole-value synthesis, then scan.**
[Unchanged from my proposal, and codex's is close enough that I would take
either.] Never commit a captured byte. Codex's field allowlist before
substitution is a good addition to my generator. Agy's blacklist scrubbing is
the one option that should be off the table (2.8).

**4. Slices: codex takes the spine, I take the read plane, agy takes delivery
surfaces, and skills move out of delivery.** Codex and agy both claimed the
spine (2.11); record 003's prior assignment and codex's stronger schema
(3.3, 3.4) settle it for codex. Delivery surfaces is unclaimed and oversized
(1.7); agy is the only one of us who wrote the `ai-log-depot` CI path
concretely and should own it, with skills split off as a separate small piece so
the admin UI and the deploy do not queue behind each other. Make the
registration record an open versioned mapping so the `contracts.py` barrier does
not recur (1.6).

**5. Estimate: 12 to 21 resident-days, 6 to 8 elapsed rounds.** Codex's band and
mine agree within noise. Agy's 3 to 4 calendar days is not credible at this
scope (2.9) and should not enter the plan.

**6. Two things the orchestrator should act on before code starts.** The
service-account scope blocker (1.9): the delivered credential sees 4 objects and
zero VMs, so Gate 1 demonstrates an empty inventory no matter how correct the
server is, and the lab-admin round trip is slower than the build. And agy's
FastMCP identity-injection question (3.5), because three proposals depend on
that mechanism and none of us has verified it.

**7. `OpsToken`.** Per record 006, unanimous on the measurement, and the
reference client's alias is a comment rather than a reason (2.10).
