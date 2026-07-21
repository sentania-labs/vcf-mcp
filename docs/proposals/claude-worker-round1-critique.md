# claude-worker, round 1 critique

Phase 2. I read `codex/round1-architecture` at `86b3404` and
`agy/round1-architecture` at `68e30bd` read-only via `git show`. I entered
neither worktree.

Two facts I re-verified before writing, so my attacks are checkable:

- `mcp==1.28.1` in a throwaway `/tmp` venv. `mcp/server/` contains
  `sse.py`, `streamable_http.py`, `streamable_http_manager.py`, and a
  bundled `fastmcp/`. All three import.
- `X-Ops-API-use-unsupported` appears as the internal-API header in
  `vcf-content-factory/reference/docs/internal-api-9.1.json` (20+ hits).

My own DEVEL measurements from phase 1 are cited below where they bear on a
peer's claim: 142 action definitions / 66 distinct display names / zero
parameter metadata in the list response; 508 resources at 1,097,361 raw
bytes falling to 96,357 field-projected; 53% of the raw resource payload is
HATEOAS `links`; 74 report definitions at 114,293 bytes; 1,113 alerts.

---

## Part A: codex-worker

### Steelman

The list response for action definitions carries no parameter metadata, so
dynamic tool generation cannot produce a faithful schema at any tool count.
Therefore fix the surface, put the catalog behind a dispatcher, and make
`apply` accept nothing but a plan ID plus an HMAC token bound to key
identity, target, posture, and a parameter digest, so the authorization
decision is made once at plan time and cannot be re-litigated by a client
payload at apply time. The implicit premise worth supplying: the security
boundary is not the tool schema, it is the plan record, which is why the
tool surface can be small and boring.

This is the strongest of the three proposals. Two places where it beats
mine outright, and I was wrong:

- **`outcome_unknown`.** Codex names the state where a one-use plan is
  consumed and the upstream submission then times out, and rules out
  automatic retry. My proposal consumes the plan and does not say what
  happens on an ambiguous outcome. That is a real hole in mine and codex's
  answer is correct. Adopt it.
- **AEAD associated data.** Binding ciphertext to (schema version, target
  ID, field purpose, key ID) so a record cannot be moved between rows is
  more specific than my envelope design and is strictly better. Adopt it.

### C1. The catalog fingerprint invalidates plans for unrelated reasons

**Attacking:** fork 1, "recheck ... catalog fingerprint" at apply.

The fingerprint is over the whole catalog. Measured: 76 of the 142
definitions are APPOSUCP "Configuring \<app\> plugin" entries against
`Endpoint` resources, which churn when anyone touches application
monitoring. Installing one management pack, or an endpoint appearing,
changes the fingerprint and therefore invalidates every outstanding plan,
including a plan for `VMWARE-Power Off VM` that is byte-identical before
and after. At 10 targets with any pack activity this is a recurring
false refusal, and the operator response to recurring false refusals is to
stop trusting the check.

**Instead:** fingerprint the single definition record the plan names, plus
its `contextResourceKindKey`, not the catalog. Same safety property,
no cross-talk.

### C2. CI-held DEVEL credentials, constitution conformance

**Attacking:** fork 6, "run outside normal CI unless an approved secret is
available."

Acquiring an `OpsToken` requires a username and password. Putting a DEVEL
credential into repo Actions secrets so a CI job can acquire one
**violates the constitution rule "No lab credentials or secrets ever enter
this repo, CI, logs, or transcripts."** The CI carve-out in Pinned tooling
is explicitly for deployment configuration, "which is not credentials".
Codex frames this as needing "a decision plus an endpoint-specific
compatibility test", which is the wrong instrument: a decision record
cannot weaken an invariant, and the constitution routes anything that
"weakens an invariant above" to Scott.

**Instead:** DEVEL contract tests are an operator-run local target only,
never a CI job, and CI runs fixture-backed tests exclusively. If the team
wants CI-side live testing it goes to Scott as an escalation, not to
`docs/decisions/`.

### C3. The keyring sits next to the ciphertext it protects

**Attacking:** fork 3, "a small versioned JSON keyring on the secrets
volume", plus the risk bullet conceding it "protects database-only theft".

For a single container with the SQLite database and the keyring both on
mounted volumes, "database-only theft" is a threat that barely exists:
whoever can read the `.db` file can read the `.json` file next to it. The
design as written buys protection against a database dump copied without
the filesystem, and codex's risk bullet is honest about this, but the fork
still presents encryption at rest as the load-bearing control.

**Instead:** either name the separate volume and state what enforces the
separation (different mount, different ownership, not present in the same
backup blob), or derive the key-encryption key from a passphrase injected
at container start so the volume alone is insufficient. Pick one and say
which, because the difference is the entire threat model.

### C4. Unknown-action-ID as a cache-bust is an amplifier

**Attacking:** fork 1, catalog refreshes on "a requested unknown action ID".

That makes cache invalidation client-controllable. A client looping on
garbage action IDs forces a full catalog refetch per call. Measured, that
is a 43,009-byte paginated fetch per miss, and at 10 targets an
authenticated read-only key can generate sustained load against every
registered appliance while never doing anything the audit log would flag as
suspicious. The 15-minute TTL does not bound this, because the miss path
bypasses it by design.

**Instead:** rate-limit refresh independently of the TTL (at most one
refresh per target per N seconds regardless of miss count), and serve the
cached miss as a miss.

### C5. No response-shaping story anywhere. This is the biggest hole.

**Attacking:** fork 6 and the read-only tool slice generally.

Codex specifies pagination normalization and tolerant parsing, and never
once addresses payload size. Measured on DEVEL, which is a small lab:
`/api/resources` at 508 resources is 1,097,361 bytes raw, roughly 274k
tokens, and 53% of that is HATEOAS `links` no model will ever follow.
Field projection takes the same 508 resources to 96,357 bytes, a 92%
reduction. `/api/reportdefinitions` is 74 definitions at 114,293 bytes,
about 28k tokens, and fork 6 proposes to "list definitions only" in Phase 1
as if that were the cheap option.

A correct, audited, well-authorized tool that returns 274k tokens is a tool
nobody can use. Codex's proposal would ship Phase 1 and discover this on
first contact with a client.

**Instead:** field projection and a server-side result cap belong in the
adapter layer in fork 6, alongside pagination normalization, with the
projection set per resource family and an explicit opt-in for full fidelity.

### C6. Per-key `tools/list` is a support burden that buys nothing

**Attacking:** fork 2, "Read-only API keys should not see `apply_action` in
`tools/list`."

Codex already has authoritative server-side scope, posture, and prod checks,
and says so in the same paragraph. So the variable surface adds no security.
It does add a failure mode: VCF Private AI Services is a tool-calling-only
consumer that registers a tool set at configuration time. Configure it once
with an actions-capable key, later rotate to a read-only key, and the
client's registered surface no longer matches the server's. Debugging "the
tool list depends on which key you used" is worse than debugging a clean
denial.

**Instead:** one fixed surface for all keys; `apply_action` returns a
structured denial naming the missing condition.

### C7. Stateless HTTP versus the `current` alias

**Attacking:** fork 2 ("stateless HTTP") against fork 5 (a `skill://<slug>/current` alias).

Stateless HTTP forgoes `resources/list_changed` and subscriptions. Fork 5's
whole point is that `current` advances when a release adds a version, which
is exactly the event a subscribed client would want. This is probably the
right trade for v1, but codex should say it is knowingly forgoing
notification rather than leaving two forks that quietly disagree.

---

## Part B: agy-worker

### Steelman

Do not generate one tool per action definition, because the client context
cost is unmanageable; expose a small static action pipeline instead, keep
the ASGI stack under direct control so an API-key middleware can be
inserted, server-render the admin UI to avoid a JS build step, and treat the
offline 9.1 OpenAPI as unreliable against a live 9.0.2 appliance, tolerating
unknown fields rather than binding to generated models. Supplied premise:
every one of those is the same bet, that the offline artifact and the
convenient abstraction both lie, so keep the surface fixed and the stack
visible.

The conclusions are mostly right. Nearly every argument offered for them is
wrong, and three of the six forks contain a factual error.

### A1. Fork 2 is factually wrong about the SDK

**Attacking:** "The reference MCP Python SDK (`mcp.server.sse`) integrates
cleanly", and risk 4, "If Streamable HTTP means something other than
standard SSE ... requiring us to fork or heavily wrap the transport layer."

`mcp.server.sse` is the deprecated HTTP+SSE transport from the 2024-11-05
spec. Streamable HTTP is a different transport and the SDK already ships it:
verified in `mcp==1.28.1`, `mcp/server/` contains both `streamable_http.py`
and `streamable_http_manager.py` as separate modules from `sse.py`. So
proposing `mcp.server.sse` proposes the wrong transport for the deliverable,
and agy's single named blow-up risk, the one thing flagged as capable of
wrecking the estimate, does not exist.

The fork is also a false dichotomy. It sets "reference MCP Python SDK" against
"FastMCP" as separate frameworks. `mcp.server.fastmcp` is bundled inside the
official SDK and imports fine at 1.28.1. Choosing the reference SDK does not
mean declining FastMCP. Codex gets this right and agy does not.

**Instead:** the real fork is bundled `mcp.server.fastmcp` versus
`mcp.server.lowlevel`, mounting the Streamable HTTP ASGI app. Nothing here
argues against the bundled layer.

### A2. Fork 1's stated reason is not the reason, and agy's own design knows it

**Attacking:** "hundreds of definitions ... would explode the client context
window."

The count is assumed, not measured. Measured on DEVEL 9.0.2 it is 142, and
142 is not by itself an explosion. The actual disqualifier is that
`GET /api/actiondefinitions` returns nine keys per record and **no parameter
metadata at all**; parameters come only from a populate call that requires a
concrete `contextResourceId`. Agy's own `get_action_parameters(target_id,
action_id, resource_id)` tool concedes this exactly, taking a resource ID
because it must, without noticing that the concession destroys the fork's
stated reasoning and replaces it with a much stronger one.

There is a second measured fact agy's framing misses: 142 definitions carry
only 66 distinct display names, because the catalog returns one entry per
(action x resource context) pair. Any name-keyed generation scheme emits
collisions. Worth having in the record whichever way the synthesis goes.

### A3. Fork 3 confuses Fernet with AES-GCM

**Attacking:** "encrypted at rest using AES-GCM (via the `cryptography`
library's Fernet or raw AESGCM)".

Fernet is AES-128-CBC with HMAC-SHA256, not AES-GCM. They are not
interchangeable and the parenthetical reads as if the choice were cosmetic.
They differ in key size, in whether associated data can bind ciphertext to a
row (Fernet cannot, which is precisely codex's C-side improvement), and in
rotation model. A credential-store fork that cannot name its own primitive
is not ready to be a decision record.

### A4. Audit is absent. Constitution conformance.

**Attacking:** the whole proposal.

The word "audit" appears once, as "audit log viewing" in the admin UI fork.
There is no audit write path, no key identity capture, no args digest, no
result status, no durability story. This **violates the constitution rule
"Every tool call is audited ... No tool path ships without its audit write."**
It is not an omission of detail; the proposal designs an admin screen for
reading a log it never designs writing.

**Instead:** a single audited execution wrapper that every tool passes
through, as codex specifies.

### A5. Read-only default and the prod hard block are unaccounted for

**Attacking:** fork 1's `apply_action(plan_id)`.

`apply_action` takes a plan ID and nothing else, and the proposal never
describes what is rechecked at apply. Nowhere in the document do the words
read-only default, per-target posture, or the prod appliance appear. Two
constitution invariants are therefore unaccounted for: "Read-only is the
default posture, per target" and "The prod appliance is hard-blocked from
actions." A `plan_id` with no binding to key identity, target, posture, or
expiry means any actions-capable key holding any plan ID executes it, and a
plan created while a target was action-enabled still applies after an
operator sets that target back to read-only.

**Instead:** bind the plan to key identity, target ID, posture at plan time,
parameter digest, and a short expiry; recheck posture, prod status, and key
scope at apply; consume once. Codex's fork 1 is the model here.

### A6. Five new dependencies, no escalation

**Attacking:** forks 2, 3, 4.

FastAPI, Jinja2, `cryptography`, bcrypt, and Pydantic are all proposed and
none is flagged for escalation. The constitution routes "new dependencies"
to the principal, and codex explicitly names its two and says they need
Scott's approval. Agy's proposal reads as if the team could adopt these on
its own.

Separately on bcrypt: it truncates input at 72 bytes, which is a real
footgun for a bootstrap admin password fed from a generated secret. Codex's
scrypt choice avoids it. And FastAPI on top of the SDK's Starlette adds a
framework for routing and validation that a five-form admin UI does not
need.

### A7. `get_skill` reads from disk with no named validation

**Attacking:** fork 5, "static `list_skills()` and `get_skill(skill_name)`
MCP tools that read the markdown files from disk."

No slug validation is specified, so `get_skill("../../../data/creds.db")`
is the obvious first thing an adversarial client tries, and the credential
store lives on a mounted volume in the same container. Codex explicitly
closes this ("does not read arbitrary paths") and agy does not. Serve only
from a validated in-memory index built at startup.

Also, "the server will discover them on boot" plus no version or digest
means a client cannot cite which revision of a skill it acted on, which
matters once Phase 3 mining starts adding content. Codex's immutable
`<slug>/<semver>/` with a checked-in digest index is better and I concede it
is better than my own fork 5 framing too.

### A8. The estimate is for a subset of the work

**Attacking:** "15 to 20 agent hours."

The four line items cover the server shell, admin UI, credential store,
client, and read tools. There is no line for the audit subsystem, none for
skills exposure across four surfaces, none for the container build or CI,
none for plan/apply, none for fixtures. Codex costs the same phase at 12 to
18 worker-days. That is not a difference of opinion about velocity, it is a
different scope, and the synthesis should not average them. Agy's number
should be rebuilt against the same work breakdown before it is compared to
anything.

### A9. `list_action_definitions` requires a resource kind it cannot know

**Attacking:** fork 1's `list_action_definitions(target_id, resource_kind)`.

Measured, the catalog spans 10 distinct `contextResourceKindKey` values and
5 adapter kinds. A model that has just been handed a resource ID does not
reliably know its kind key, so a required `resource_kind` forces either a
guess or a 10-way enumeration. Make it an optional filter, with the
unfiltered call returning a projected summary.

---

## Where this leaves the synthesis

Codex's fork 1 plan binding (plus `outcome_unknown`), fork 3 associated-data
envelope, and fork 5 immutable versioned skills should carry, over both mine
and agy's. My measured DEVEL numbers should carry as the grounding for fork
1 and for the payload-shaping requirement that neither peer has. Agy's
correct conclusions (static tools, server-rendered UI, tolerant parsing)
survive, but none of its stated reasoning should be quoted into a decision
record.

Two items need Scott, not the team: codex's CI-held DEVEL credential (C2),
and the dependency set both peers propose (A6).

Co-authored-by: Claude <claude@team.local>
