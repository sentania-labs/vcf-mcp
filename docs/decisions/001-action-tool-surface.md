# 001: action tool surface, fixed tools with a catalog-backed dispatcher

- **Status:** accepted; both escalated questions resolved by the principal 2026-07-21; the mutation gate is amended by record `007-mutation-gate-generalization.md`
- **Amended by:** `007-mutation-gate-generalization.md` (2026-07-21). Record 007 generalizes this record's action-only plan gate to cover alert verbs and report runs, adds mandatory pre-apply revalidation, renames three tools, and removes `validate_action`. Where this record and 007 conflict on the mutation gate, **007 governs**.
- **Date:** 2026-07-20
- **Assignment:** vcf-ops-mcp round 1, architecture forks 1-6
- **Orchestrator run:** `orchestrator-run-20260720-231633`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker

## Context

Fork 1 of the round. VCF Operations exposes an actions framework whose
catalog is read from `GET /api/actiondefinitions`. The question was whether
to generate one MCP tool per action definition, expose a fixed set of tools,
or build a hybrid. Client context cost, tool-count explosion, and what VCF
Private AI Services tolerates were the stated pressures.

The decisive input was not any of those. It was measurement.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/round1-architecture` | `85cf71244b042709972e8fce4240b3b916965147` |
| codex-worker | `codex/round1-architecture` | `86b3404056be6f67337294dd47bedb477df6a84b` |
| agy-worker | `agy/round1-architecture` | `68e30bdec4329cdb65af5a278ed3388675ba6046` |

**claude-worker** did read-only recon against DEVEL and proposed 14 static
tools, of which 4 cover the entire action family, arguing that generated
schemas are structurally unavailable. **codex-worker** independently did the
same recon and proposed a fixed surface with a six-tool action family
(`list_action_definitions`, `populate_action`, `validate_action`,
`plan_action`, `apply_action`, `get_action_task`) plus a persisted one-use
plan bound by HMAC. **agy-worker** proposed a hybrid with a five-tool generic
action pipeline, reasoning from an unmeasured estimate of "hundreds of
definitions" causing context explosion.

Two workers measured the same appliance and got the same numbers. That
convergence is the strongest signal this round produced.

## Measured facts, DEVEL 9.0.2, 2026-07-20

These are load-bearing and both claude-worker and codex-worker report them
independently:

| Measurement | Value |
| --- | --- |
| `GET /api/actiondefinitions` `totalCount` | 142 |
| `type` field across all 142 | `UPDATE`, every one |
| Parameter metadata in the list response | none |
| Distinct `displayName` across 142 defs | 66 |
| Distinct `contextResourceKindKey` | 10 |
| Distinct `actionAdapterKindKey` | 5 |
| `/api/resources` raw at 508 resources | 1,097,361 bytes (~274k tokens) |
| Same 508, field-projected | 96,357 bytes, 92% reduction |
| Share of raw resource payload that is HATEOAS `links` | 53% |

## Critique (phase 2, adversarial)

**claude-worker on agy-worker (A2):** the stated reason for rejecting dynamic
generation is wrong even though the conclusion is right. 142 is not by itself
an explosion. The actual disqualifier is that the list response carries no
parameter metadata; parameters arrive only from a populate call requiring a
concrete `contextResourceId`. agy's own `get_action_parameters(target_id,
action_id, resource_id)` tool concedes this by taking a resource ID because
it must, without noticing the concession destroys its own stated reasoning.
Also: 142 definitions carry only 66 distinct display names, so any name-keyed
generation scheme emits collisions.

**claude-worker on agy-worker (A5, A9):** `apply_action(plan_id)` binds to
nothing. The words read-only default, per-target posture, and prod appliance
appear nowhere in agy's proposal. `list_action_definitions(target_id,
resource_kind)` requires a kind key the model cannot reliably know across 10
distinct values.

**claude-worker on codex-worker (C1):** the whole-catalog fingerprint
invalidates plans for unrelated reasons. 76 of 142 definitions are APPOSUCP
entries that churn when anyone touches application monitoring, so installing
one management pack invalidates every outstanding plan including a
byte-identical `VMWARE-Power Off VM`. Recurring false refusals train operators
to stop trusting the check.

**claude-worker on codex-worker (C4):** refreshing the catalog on "a requested
unknown action ID" makes cache invalidation client-controllable. A client
looping on garbage IDs forces a 43,009-byte refetch per miss, across every
registered target, without tripping anything the audit log flags.

**claude-worker on codex-worker (C5):** no response-shaping story anywhere.
A correct, audited, well-authorized tool returning 274k tokens is a tool
nobody can use.

**claude-worker on codex-worker (C6):** per-key `tools/list` filtering buys no
security given authoritative server-side checks, and breaks tool-calling-only
clients that register a surface once at configuration time.

**codex-worker on claude-worker (1, 2):** a checked-in global action allowlist
gives one compromised actions-capable key every globally allowed action across
its targets. A body hash proves only the client did not alter the plan; it
does not prove resource, defaults, catalog, posture, or key authorization
stayed valid. A timeout must end in `outcome_unknown`, never automatic retry.

**codex-worker on agy-worker (1):** `apply_action(plan_id)` names no binding to
key identity, target posture, prod identity, catalog fingerprint, expiry, or
one-use consumption. A local cache alone is replayable and stale.

**agy-worker conceded in full:** "The blocker for dynamic tool generation is
missing metadata, not tool count. [...] This structural reality kills my
'hundreds of definitions' context-explosion argument. [...] They are right,
and I was wrong."

## Decision (phase 3, synthesis)

**No dynamic tool generation.** All three workers converged on this, and the
reason of record is codex-worker's and claude-worker's measured one, not
agy-worker's: the catalog carries no parameter metadata, so a generated tool
cannot have a faithful schema at any tool count. The 66-distinct-names-across-
142-definitions collision is recorded as a second independent disqualifier.

**A fixed action family of six tools**, codex-worker's set, carries over
claude-worker's four. The finer split keeps `populate` and `validate` as
separate auditable boundaries rather than folding them into plan construction.

**The security boundary is the plan record, not the tool schema.** Persist a
one-use plan holding a random plan ID, key identity, target ID, action ID,
resource IDs, normalized parameter digest, definition fingerprint, target
posture, and expiry. `apply_action` accepts only a plan ID plus an opaque
HMAC-bound token, never a fresh action payload. At apply, atomically claim the
plan, then recheck every predicate: expiry, key scope, target action
enablement, prod hard block, definition fingerprint, parameter digest.

**Grafted from claude-worker over codex-worker's original:** fingerprint the
single definition record the plan names plus its `contextResourceKindKey`, not
the whole catalog (C1). Rate-limit catalog refresh independently of TTL and
serve a cached miss as a miss (C4). One fixed tool surface for every key, with
`apply_action` returning a structured denial naming the missing condition,
rather than per-key `tools/list` filtering (C6). `list_action_definitions`
takes `resource_kind` as an optional filter (A9).

**Grafted from codex-worker over claude-worker's original:** `outcome_unknown`
as an explicit terminal state for a consumed plan whose upstream submission
timed out, with no automatic retry. claude-worker conceded this: "That is a
real hole in mine and codex's answer is correct. Adopt it."

**Field projection is a Phase 1 requirement, not an optimization** (C5).
Projection sets per resource family, a server-side result cap, and an explicit
opt-in for full fidelity, all in the adapter layer. A tool that returns 274k
tokens does not ship.

**Every tool call routes through one mandatory audited dispatcher.** Registration
must fail, or execution be impossible, without that wrapper. HTTP middleware is
for request identity and correlation only: codex-worker's point 3 is correct
that Streamable HTTP request count does not equal tool-call count, so
middleware alone cannot satisfy the audit invariant.

**Actions remain disabled regardless of any of this** until Scott's Phase 2
gate. This record designs the path; it does not open it.

## Escalated to the principal, and resolved

Two questions in this fork were Scott's, not the team's, because both widen
action blast radius. **Both were resolved by Scott on 2026-07-21.** The
questions as escalated, and the rulings, follow.

### 1. Action authorization granularity

**As escalated.** codex-worker argues a global allowlist means one compromised
actions-capable key gets every allowed action across its target allowlist, and
proposes per-key action-class subsets intersected with a global server policy,
default empty. The team recommends the intersected model. The seed allowlist
contents and the granularity choice widen blast radius and go to Scott.

**Ruling: fine-grained, default-deny.** Each API key carries a specific
allow-list of action-classes, intersected with a global policy. A newly minted
key can do **nothing** until scopes are explicitly granted. This adopts the
team's recommended intersected model and sharpens the default: the empty set is
not merely the default, it is the state a key stays in until someone grants
otherwise.

### 2. Whether actions-scoped API keys may be minted before the Phase 2 gate

**As escalated.** Raised by claude-worker. The team's recommendation is no: the
mint path exists in code but refuses until the gate.

**Ruling: generalized past the question asked.** Scott replaced the
action-specific rule with one general rule covering every capability:

> A scope is only **assignable** if the server actually implements the matching
> capability, read or write.

So there is no minting a `read_logs` scope when no `read_logs` tool exists, and
action scopes are not grantable until the action machinery ships and clears the
Phase 2 gate. The grantable-scope set is **derived from what is implemented**,
which means there are no phantom grants.

Record 007 makes this structural rather than a rule anyone has to remember: the
grantable-scope registry is derived at server start from the adapters actually
registered, the admin UI enumerates that registry, and a scope no registered
adapter claims cannot appear in the UI and therefore cannot be granted.

## Division of labor

Prospective, for the Phase 1 build round.

| Piece | Assigned to | Why this harness |
| --- | --- | --- |
| Plan/apply pipeline, one-use plan store, apply-time revalidation, `outcome_unknown` | codex-worker | It designed the plan-as-security-boundary model and the adversarial authorization cases; its critique found the binding gaps in both peers |
| Audited dispatcher, structural enforcement that no tool registers without it | codex-worker | Its own critique point 3 identified why middleware cannot satisfy the invariant; it should build the thing it specified |
| Field projection and result caps in the adapter layer | claude-worker | It measured the payloads and is the only resident that treated response shaping as a correctness requirement |
| Catalog cache, TTL, per-definition fingerprint, refresh rate limiting | claude-worker | Its C1 and C4 are the specification for this piece |
| `list_action_definitions` filtering and projected summaries | agy-worker | Defensive JSON shaping against a live catalog is its stated strength, and this piece is read-only so its weaker safety-model showing this round carries no risk here |

## Dissent

agy-worker's proposal lost on fork 1 and it conceded rather than dissenting.
Its concession is recorded verbatim above. No standing dissent on this record.

claude-worker's global allowlist lost to codex-worker's intersected model, and
claude-worker did not contest it in ballots. codex-worker's whole-catalog
fingerprint lost to claude-worker's per-definition fingerprint, and
codex-worker did not contest it.

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
