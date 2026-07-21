# Codex worker, round 2 mutation-gate proposal

- Timestamp: 2026-07-21T17:23:08Z
- Branch: `codex/r2-mutation-gate`
- Protocol: phase 1 blind proposal

## 1. Approach

Amend record 001 around a generalized mutation gate with typed family
adapters. The public tools should be `plan_mutation(target_id, operation,
input)` and `apply_mutation(plan_id, confirmation_token)`. `operation` is a
closed enum initially containing `action`, `alert_ack`, and `report_run`.
`input` is a discriminated union with a bounded schema for each operation:

- `action`: `action_id`, `resource_ids`, and explicit parameter inputs.
- `alert_ack`: one or more alert IDs.
- `report_run`: report definition ID and the supported run inputs, including
  resource IDs and output options if the target API contract supports them.

This replaces `plan_action` and `apply_action`; it does not create six more
family-specific tools. The other action tools remain
`list_action_definitions`, `populate_action`, and `validate_action`.
`get_action_task` becomes `get_mutation_status`, which can project either a
locally terminal plan result or the upstream task/report-run status. Thus the
six-tool action family stays six tools, while the existing alert and report
families retain their read tools. Alert acknowledgement and report run have no
direct mutation tools outside this gate.

The obvious dedicated-plan alternative makes schemas marginally easier to
discover but duplicates the security boundary and increases the fixed surface
by four tools. A fully generic untyped payload would minimize tools but would
erase useful input contracts. A closed discriminator plus a union keeps one
gate, gives clients operation-specific schemas, and makes unsupported mutation
families fail closed. Adding a mutation requires adding its enum member,
schema, policy class, planner, revalidator, submitter, status projection, and
tests. Registration or dispatch must reject an incomplete family adapter.

Persist a one-use plan with at least:

- random `plan_id`, HMAC-bound `confirmation_token`, schema version, creation
  and expiry times, and state;
- key identity, target ID, operation discriminator, required capability scope,
  target posture snapshot, and normalized policy-class identifier;
- canonical normalized intent, `intent_digest`, redacted operator summary,
  and a family-specific `subject_snapshot` plus `subject_fingerprint`;
- family-specific effective payload produced at plan time,
  `effective_payload_digest`, and upstream correlation/task identifiers once
  submission begins.

The HMAC covers the plan identity and immutable digests. Canonicalization is
versioned and server-owned. Raw secrets are never plan fields or audit data.
The subject fingerprint is not one universal upstream concept. It is the hash
of a versioned, family-specific projection of safety-relevant facts:

- For `action`, it contains the selected action-definition record and
  `contextResourceKindKey`, plus resource identities and the canonical
  populated/validated effective parameters. This preserves record 001's
  per-definition scope and does not hash the whole catalog.
- For `alert_ack`, it contains each alert ID, target/resource association,
  current acknowledgement state, and any API fields that determine whether
  acknowledgement is still applicable. Volatile presentation fields such as
  timestamps that do not alter applicability are excluded.
- For `report_run`, it contains the report-definition identity and a canonical
  projection of its current runnable configuration, the selected resource
  identities, and the normalized effective run payload. A definition family
  without a safe detail/readback contract does not implement `report_run` and
  its scope cannot be granted.

`apply_mutation` atomically changes an unexpired plan from `ready` to
`claimed` before any upstream work. It then rechecks key validity, target
allow-list membership, the fine-grained operation scope, global policy,
target action enablement, and the unconditional prod block. These checks apply
equally to all three operations. Calling an acknowledgement or report run an
action for gating means the target toggle and prod refusal are structural,
not merely properties of the actions API adapter.

After policy checks, apply performs a family preflight immediately before its
mutation POST:

- `action`: refetch the named definition, repopulate using the stored resource
  IDs and explicit inputs, then call the VCF Ops validation operation where
  available. Recompute both fingerprints. The submit payload is the newly
  validated effective payload, never blindly the stored bytes.
- `alert_ack`: refetch every named alert through the read adapter. Require all
  to exist, remain associated with the planned subjects, and remain
  acknowledgeable and unacknowledged. Recompute the subject fingerprint.
- `report_run`: refetch the report definition and referenced resources, rebuild
  the run request from the stored normalized intent, and validate all locally
  knowable constraints exposed by those responses. Recompute the definition,
  subject, and effective-payload fingerprints. If DEVEL recon finds a
  side-effect-free server validation endpoint, call it too; lack of such an
  endpoint must not be disguised as validation.

Any changed fingerprint, populated default, applicability result, or effective
payload refuses submission. The claimed plan ends as `stale`, with a redacted
field-level reason, and the operator must call `plan_mutation` again and
confirm the new plan. Apply must not silently create a replacement confirmed
plan, because confirmation belongs to the exact summary and payload the
operator saw.

A preflight error or timeout occurs before mutation and ends the consumed plan
as `preflight_failed`; the response states that no mutation was submitted. A
new plan is required. This costs, per apply, roughly two to three upstream
calls for an action (definition read, populate, validation), one batched or N
bounded reads for N alerts, and two or more reads for a report (definition and
resources, plus validation if available). Cap batch size so freshness does not
become an unbounded apply-time workload.

Only uncertainty after the mutation request may have reached VCF Ops produces
`outcome_unknown`. Persist `submitting` before the POST. A timeout, disconnect,
or ambiguous response after that point consumes the plan permanently as
`outcome_unknown`, records any correlation identifier available, and never
automatically retries. A definite upstream rejection is `submission_failed`;
an accepted synchronous result is `completed`; an accepted asynchronous result
is `submitted` and is followed through `get_mutation_status`. Every transition
gets a durable audit result.

Scopes should be capability-derived and default-deny. I propose
`mutate.action:<policy-class>`, `mutate.alert_ack`, and `mutate.report_run`, all
intersected with global policy. The action class suffix uses the stable policy
classification selected by implementation, not an operator-supplied value.
No mutation scope is grantable merely because its enum value exists. It becomes
grantable only when that adapter and its tool-visible capability are registered
as implemented and, for action machinery, after the Phase 2 gate. A new key
has an empty mutation allow-list. Read scopes remain similarly derived from
implemented read capabilities.

Planning itself should require target access and the matching implemented
capability, but applying is the irreversible authorization boundary and repeats
every check. A read-only target, disabled action toggle, prod target, revoked
key, removed scope, or policy denial refuses server-side even if a valid token
was issued earlier.

## 2. Risks

The generic union may be rendered poorly by some tool-calling-only clients. If
VCF Private AI Services cannot select or validate discriminated union branches,
dedicated typed planners with one generic `apply_mutation` would be the better
hybrid. That preserves one security boundary at a cost of two additional tools,
rather than duplicating apply logic.

Alert freshness has a race between the final GET and acknowledgement POST. No
client-side preflight removes that TOCTOU interval. If the API provides an
optimistic version, ETag, or conditional update, the adapter should use it. If
not, an already-acknowledged response should be reported as a definite
idempotent conflict, not success invented by the server. Multi-alert
acknowledgement may also be partially applied upstream. If the endpoint is not
atomic, the plan and audit model need per-alert outcomes and must never retry
the whole batch automatically.

Report APIs may expose a mutable schedule/template model whose runnable
configuration cannot be reconstructed from one definition read. They may also
return a generated report ID synchronously rather than an ordinary task ID.
`get_mutation_status` therefore needs a typed status projection, not an
assumption that every mutation uses the actions task endpoint.

Repopulating actions can itself produce nondeterministic defaults. Strict
digest equality may reject harmless drift and frustrate operators, but allowing
the server to classify drift as harmless weakens confirmation. I prefer strict
refusal first, with later field-specific stability rules only after measured
evidence and a recorded policy change.

Claim-before-preflight prevents replay but makes transient read failures consume
plans and enables a caller with valid confirmation tokens to burn its own
plans. That is an acceptable fail-closed trade, though short plan lifetimes and
rate limits still matter. The extra reads add latency and upstream load. Batch
caps, deadlines, and per-target concurrency limits are required, but cached
data cannot satisfy apply-time freshness.

Given one hour and one question against DEVEL, I would use read-only Swagger
and GET recon to answer: what exact endpoints, response fields, conditional
headers, batch semantics, and task identifiers exist for alert acknowledgement
and report execution on 9.0.2? I am most unsure about atomicity and whether
either family offers a side-effect-free validation or version precondition.
No live mutation is needed to answer the contract-shape portion.

## 3. Division-of-labor claim

I am best suited to own the generic plan state machine, canonical digest
contract, family adapter interface, apply-time authorization/revalidation
ordering, and failure-state tests. This is the security boundary I originally
argued for, and the dropped freshness check came from my critique.

The resident who performs the DEVEL read-only recon is better suited to own the
alert and report adapter field projections and synthetic fixtures, because
those details should follow measured 9.0.2 contracts rather than my inferred
shape. A separate peer should test the tool schema against the Private AI
Services client before the team commits to discriminated unions over the
hybrid typed-planner fallback.

## 4. Rough estimate

Amending record 001 after synthesis is about half a day. A production-quality
implementation is roughly 5 to 8 engineer-days: 2 to 3 for the plan store and
state machine, 1 to 2 for action revalidation, and 2 to 3 for alert/report
adapters, scopes, fixtures, audit coverage, and client-schema tests.

This becomes 2 to 3 weeks if DEVEL shows non-atomic bulk acknowledgement,
report definitions whose effective configuration spans several undocumented
resources, no usable conditional/version fields, or a client that cannot
consume the union schema and therefore forces a tool-surface redesign.
