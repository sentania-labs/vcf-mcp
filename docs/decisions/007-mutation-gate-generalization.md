# 007: mutation gate generalization and pre-apply revalidation

- **Status:** accepted, with one SPEC contract error escalated to the principal
- **Date:** 2026-07-21
- **Assignment:** vcf-ops-mcp round 1, continuation: external review findings on PR #1
- **Orchestrator run:** `vom-r2-esc-20260721-171423`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker
- **Amends:** record `001-action-tool-surface.md`, sections "Decision (phase 3, synthesis)" and "Escalated to the principal"

## Context

PR #1's external Codex review raised two P1 findings against record 001. Both
were accepted without debate; how to fix them was the question this round
deliberated.

**Finding 1, verbatim:**

> For the required alert-acknowledgement and report-run operations in
> `docs/SPEC.md`, this plan shape is action-definition-specific and requires an
> action ID and definition fingerprint, even though those operations use
> separate API families. The source proposal explicitly said both would use the
> shared plan service, but the accepted record omits that mapping and exposes
> only `plan_action` and `apply_action`; implementers must therefore either omit
> these MVP operations or add an unrecorded mutation path that bypasses the
> mandatory plan gate. Define a generalized operation type and payload
> fingerprint, or specify dedicated plan/apply paths for both families.

**Finding 2, verbatim:**

> When resource state, parameter applicability, or populated defaults change
> between planning and applying, every check listed here can still pass: the
> parameter digest only proves the stored parameters were not modified, and the
> catalog record is explicitly documented as containing no parameter metadata.
> The accepted critique in `docs/proposals/codex-worker-round1-critique.md`
> required repopulating or validating against VCF Ops before mutation, but that
> freshness check was dropped from the synthesized decision, allowing a stale
> plan to execute a destructive action.

The two were dispatched as one assignment, on the orchestrator's reading that
they are coupled: where revalidation hooks depends on how the gate generalizes,
and "revalidate" cannot mean the same call for an action, an alert verb, and a
report run. All three workers accepted the coupling. claude-worker sharpened it
usefully: the two are coupled at the plan record and **separable at the failure
model**, because revalidation runs entirely before submission and therefore can
never produce `outcome_unknown`.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/r2-mutation-gate` | `ce6e6c05c166edf29bfc2f31a0041a370df0fc7e` |
| codex-worker | `codex/r2-mutation-gate` | `63567bf885c6a6fda1365ba3122c22c3fdcc8b45` |
| agy-worker | `agy/r2-mutation-gate` | `a08f6ae0ad64f4d3e2d1a05fab7fefc00e7d55e4` |

Blindness was verified structurally: each phase-1 branch contained exactly one
new file, its own proposal, and no branch ever held a peer's artifact.

All three independently rejected dedicated per-family plan/apply paths and
converged on one generalized gate. claude-worker's reason is the one of record:
a security gate implemented three times is a gate that is correct in at most one
place, and the shared predicates (read-only check, prod hard block, atomic
one-use claim, expiry, scope intersection) would each get written three times.
That is the same failure shape as finding 1 itself, which happened because the
action family got a gate and the other two families got nothing.

## Critique (phase 2, adversarial)

The critique round produced the discovery that reshaped the assignment.

### The measured facts

Verified independently by the orchestrator against
`vcf-content-factory/reference/docs/operations-api-9.1.json` before synthesis,
because both are load-bearing and both contradicted a phase-1 proposal:

| Fact | Value |
| --- | --- |
| Occurrences of `acknowledg` in the entire 9.1 OpenAPI document | **0** |
| Action surface, complete | `GET /api/actiondefinitions`, `POST /api/actions/{id}`, `POST /api/actions/{id}/query`, `GET /api/actions/{taskId}/status` |
| Action validation endpoints | **none**; the only path matching `valid` is `/api/fleet-management/iam/saml-metadata/validate`, unrelated |
| Real alert verb set | suspend (`minutes`), cancel, takeownership, releaseownership, assignownership |

claude-worker's DEVEL recon (read-only, 9.0.2 build 25137838) added:

| Measurement | Value |
| --- | --- |
| `GET /api/alerts` totalCount | 1124: `status` 1086 CANCELED / 38 ACTIVE; `controlState` 1124 OPEN / 0 other |
| Alert fields returned, collection and detail identical | `alertDefinitionId, alertDefinitionName, alertId, alertImpact, alertLevel, cancelTimeUTC, controlState, links, resourceId, startTimeUTC, status, subType, suspendUntilTimeUTC, type`. **No `ownerId` or `ownerName` on any of 1124**, though the 9.1 schema declares both |
| `GET /api/alerts/{id}` cost | 926 bytes, 28 to 31 ms |
| `GET /api/reportdefinitions/{id}` on 9.0.2 | 200, 1661 bytes, fields `active, description, id, links, name, owner, subject, traversal-specs`. **No version, timestamp, or content hash** |
| `GET /api/reports/{definition-id}` | **HTTP 404**, `"No such Report"`. `/api/reports` is the run collection, not the definition collection |
| `GET /api/actiondefinitions` | 142 definitions, 43009 bytes, byte-identical across 3 calls, **no parameter metadata** |

### What the critiques established

**There is no alert acknowledgement operation.** codex-worker and claude-worker
found this independently. Two of the three proposals were built on one, and
claude-worker had itself listed a verb set in phase 1 (`acknowledge, release,
suspend, assignownership`) that does not match the API. claude-worker disclosed
its own error unprompted:

> I got the structural claim right, that the unit is a verb on a multi-verb
> endpoint, and I got the verb list wrong while presenting it as recon. The
> structural claim survives and is in fact stronger than I argued: the real verb
> set contains `cancel`, which closes an alert outright, so "the alert unit is
> an ack" is not merely imprecise, it understates the blast radius by a lot.

**agy-worker's revalidation design was falsified in all three rows.** It read
report definitions from an endpoint that returns 404 for definition IDs, hashed
a modification timestamp that does not exist on either version, and called an
action validation endpoint that does not exist. claude-worker also noted that
agy-worker's own closing paragraph named the condition that defeats its design
without noticing the condition is unconditionally true.

**agy-worker's `stale_plan` left a spin-until-you-win hole.** It never said the
plan is consumed, so a client holding a valid token could retry apply against a
flapping subject until the fingerprint momentarily matched.

**codex-worker's payload recomputation contradicted its own confirmation
principle.** claude-worker's strongest objection: codex-worker argued against
returning a fresh plan because "confirmation belongs to the exact summary and
payload the operator saw", while also specifying that the submitted payload is
recomputed at apply, "never blindly the stored bytes". Both cannot be
load-bearing, because a canonical digest matching does not mean the bytes match.

**codex-worker's own rule, turned on codex-worker.** codex-worker wrote that a
family without a safe readback contract does not implement the operation.
claude-worker measured the report-definition readback and showed it carries no
version, timestamp, or content hash.

### Concessions

Three substantive concessions, all volunteered:

**claude-worker conceded the round's sharpest split in full**, on returning a
fresh plan inside a denial:

> The server-side half of that is true and it is not the half that matters. The
> consumer of that response is usually an LLM client with a goal to complete,
> and I would be handing it a `plan_id` and a `plan_token` in the same payload
> as the denial. It can call apply immediately, and it will, and no human will
> have seen the new summary. I described the thing I must not build and then
> described the mechanism for building it two paragraphs later, in the same
> document where I insisted the record say "so nobody later implements it as
> auto-continue".

**codex-worker conceded `alert_ack` names the wrong unit**, that `report:publish`
must split from `report:run`, and that its alert fingerprint was underspecified.

**agy-worker conceded the alert unit, bulk partial-success handling, and the
`get_mutation_status` fallback**, and abandoned `alert_ack`.

## Ballots (phase 3)

Four contested questions, four ballots each: orchestrator, claude-worker,
codex-worker, agy-worker. **No question split 2-2, so the critic seat was
correctly not invoked**, per `.team/team-config.yaml`, which seats cursor as
tiebreaker-only.

| Question | claude | codex | agy | orchestrator | Result |
| --- | --- | --- | --- | --- | --- |
| Q1 alert batch size | (a) | (a) | (b) | (a) | **(a) one alert per plan, 3-1** |
| Q2 action revalidation | (c) | (c) | (c) | (c) | **(c) gate-blocking question, 4-0** |
| Q3 `plan_mutation` schema | (b) | (b) | (b) | (b) | **(b) flat optional scalars, 4-0** |
| Q4a `report:run` | (a) | (b) | (a) | (a) | **(a) ship with shallow check, 3-1** |
| Q4b `report:publish` | defer | defer | defer | defer | **defer, 4-0** |

Ballot artifacts: claude-worker `f2669cf6df73f6a24117c656ce5717c5bb64f800`,
codex-worker `74a675b3ccdf0530aef4950f5e5f9beb00c3f8ef`, agy-worker
`9486d62839dd3fb620178376ce40b934eac9d776`.

Two workers voted against their own prior positions: claude-worker returned to
the one-alert cap it had withdrawn, and agy-worker voted against the position it
had adopted in its own critique. Both said so in their interest declarations.

## Decision

### The gate generalizes; it is not duplicated

One plan record, one pair of mutation tools, one gate, with a family adapter
interface underneath. The adapter contract, not the discriminator, is what makes
the gate structural. `operation` is a **closed enum**: `action`, `alert_op`,
`report_run`. Adding a value is a decision-record change, not a code change,
which is what stops a fourth mutation family arriving unrecorded the way alerts
and reports did.

### Amended plan record

Replaces record 001's plan record field list.

| Field | Purpose |
| --- | --- |
| `plan_id` | random, one-use |
| `key_id` | minting key identity |
| `target_id` | registered target |
| `target_posture` | snapshot of read-only / actions-enabled at plan time |
| `expiry` | plan lifetime |
| `operation` | discriminator: `action`, `alert_op`, `report_run` |
| `subject_ref` | family-specific, structured, opaque to the gate |
| `payload_digest` | over the **raw serialized request bytes** the server will send. See "Submitted bytes" below |
| `precondition_fingerprint` | per-family digest over the upstream state whose change would alter what the operation means |
| `scope_required` | the per-verb scope string, checked at plan and again at apply |
| `revalidation_policy` | MVP value `strict`, the only implemented value |
| `operator_summary` | redacted human-readable summary, digest-bound to `payload_digest` |
| `schema_version` | versioned, server-owned canonicalization |

`subject_ref` per family:

- `action`: `{action_id, context_resource_ids}`
- `alert_op`: `{verb, alert_ids}`
- `report_run`: `{report_definition_id, resource_id, traversal_spec, subject, publish}`

`revalidation_policy` carries exactly one legal value on purpose. It gives a
future relaxation somewhere to be recorded instead of becoming a quiet edit to a
conditional.

### Per-family precondition fingerprints

"Fingerprint the relevant state" is not implementable. These are.

| Family | Fields hashed | Source call |
| --- | --- | --- |
| `action` | the single action definition record plus its `contextResourceKindKey`, plus the parameter set and populated defaults returned by populate for the named `contextResourceId` | `GET /api/actiondefinitions` (cached, per record 001) plus populate. **Gated: see Q2 below** |
| `alert_op` | per alert ID: `alertId`, `status`, `controlState`, `cancelTimeUTC`, `suspendUntilTimeUTC`, `alertDefinitionId`, `resourceId` | `GET /api/alerts/{id}` |
| `report_run` | report definition `id`, `name`, `subject`, `traversal-specs`, `active`, plus the context resource's `identifier` and `resourceKey.resourceKindKey` | `GET /api/reportdefinitions/{id}` plus `GET /api/resources/{id}` |

Record 001's action fingerprint hashed the catalog record alone. Measured, that
catalog carries no parameter metadata, so it was hashing the one object
guaranteed not to contain the thing that drifts. Adding populate output is the
direct fix for finding 2, and it is why Q2 matters.

`updateTimeUTC` is deliberately **excluded** from the alert fingerprint as
presentation drift, per agy-worker's flap-rate concern and codex-worker's
insistence that a versioned projection name exact safety fields.

### Q2: action revalidation is a blocking Phase 2 gate question (4-0)

There is no action validation endpoint. The only candidate revalidation call for
the action family is `POST /api/actions/{id}/query` (populate), a POST whose
side-effect-freedom nobody has proven and nobody may test without mutating.

**The record mandates pre-apply revalidation for every family.** For the action
family the source is populate, and **whether populate is side-effect-free and
byte-stable across repeated identical calls is a blocking question for the Phase
2 gate. Action apply does not ship until it is answered.**

This costs nothing in MVP: action scopes are already ungrantable before the
Phase 2 gate under record 001 and Scott's ruling 2. It converts an open risk
into a blocking question with an owner and a deadline.

agy-worker's option (b), comparing the cached definition fingerprint only and
accepting the TOCTOU gap, was rejected 4-0 including by agy-worker itself. The
reason of record is claude-worker's: the catalog carries no parameter metadata,
so cached-definition comparison is not a weaker freshness check for actions, it
is close to none, and (b) answers the external review's finding by declining to
fix it for the only family where it was found.

### Revalidation, position and failure states

Position: inside the atomic plan claim, after every authorization predicate has
passed, before any outbound mutation is composed.

Two new terminal states, both non-mutating, both consuming the plan:

- **`revalidation_changed`**: preconditions moved. Response carries
  `changed_fields` and a human-readable diff. **No `plan_id`, no `plan_token`.**
- **`revalidation_unavailable`**: the revalidation call errored or timed out.
  Never fail open, never retry automatically.

Neither can ever be `outcome_unknown`, which by record 001's definition is the
state of a consumed plan whose *upstream submission* timed out. Revalidation
runs entirely before submission, so the two cannot overlap.

**A denial never carries a usable token.** Re-planning is an explicit
`plan_mutation` call, and the operator confirms the new summary. This was the
round's sharpest split and ended unanimous. The reason of record is
codex-worker's, per claude-worker's explicit request that it be recorded in
codex-worker's form rather than as a retraction:

> The safe contract is that apply returns a denial and diff only, while an
> explicit `plan_mutation` call creates the next confirmable artifact.

### Submitted bytes: orchestrator ruling, not a ballot

claude-worker raised, and codex-worker did not answer, that recomputing the
payload at apply contradicts the confirmation principle codex-worker itself
established and that won the fresh-plan question unanimously.

**Ruling: the server submits the stored bytes.** The recomputed payload is a
comparison input to the refusal decision only, and `payload_digest` is computed
over raw serialized request bytes rather than a canonical projection.
Canonicalization is lossy by construction in exactly the dimensions that could
differ (key ordering, absent versus explicit null, numeric formatting,
whitespace), so a matching canonical digest does not establish matching bytes.
This applies codex-worker's own principle to codex-worker's payload path.

This ruling was not balloted, because it is the consistent extension of a
principle already decided 4-0 rather than a new question. It is flagged here as
orchestrator-authored so a later reader can challenge it on that basis.

### Tool surface: still six, three renamed, zero added

Record 001's tool-count reasoning binds. The mutation surface does not grow.

| Record 001 | Amended |
| --- | --- |
| `list_action_definitions` | unchanged |
| `populate_action` | unchanged, stays action-only |
| `validate_action` | **removed.** There is no upstream validation endpoint for it to call. Retaining the name would imply a server-side validation that does not exist |
| `plan_action` | `plan_mutation` |
| `apply_action` | `apply_mutation` |
| `get_action_task` | `get_mutation_status`, a **typed projection**, not an assumption that every family returns an actions task ID |

`get_mutation_status` handles three distinct handle types: actions return a
`taskId` polled at `GET /api/actions/{taskId}/status`; report runs return a
`report` object carrying `status` and `completionTime`; alert verbs complete
synchronously. A readback-only result is labelled **inferred** in the status
schema and never presented as confirmation, per codex-worker.

Removing `validate_action` drops record 001's family from six tools to five plus
whatever the read surface already carries. The count reasoning is satisfied a
fortiori.

### Q3: `plan_mutation` schema shape (4-0, flat optional scalars)

Signature: flat optional scalars and string arrays (`action_id`,
`resource_ids`, `alert_ids`, `verb`, `report_definition_id`, `parameters`),
**not** a nested discriminated union and **not** typed per-family planners.

Typed per-family planners were rejected because they split the gate along the
wrong seam: plan time is where the posture snapshot, scope resolution, and both
fingerprints are computed, so per-family planners duplicate the half of the gate
carrying the security content and share only the state transition.

Separating the normative clause from the presentational one, per claude-worker:

- **Binding:** the server validates the full field set against the named
  operation and refuses any field outside it, regardless of what the client sent
  or how it rendered the schema. A client that renders the schema badly produces
  a refusal, never a wrong mutation.
- **Revisable without a new record:** the flat-scalar shape as the default
  presentation.

Nobody has tested any shape against VCF Private AI Services. **That render-and-
validate test is a named Phase 2 gate item**, not a background hope.

### Q1: one alert ID per plan in MVP (3-1)

The documented 200 response to `POST /api/alerts` is an `alerts` array keyed by
`alertId`, which makes per-alert readback look native. It is native *for
successes*. How a failed member is represented is undocumented and cannot be
settled without mutating, so at N greater than 1 the server could record a
failed alert as succeeded, which is an audit-correctness defect rather than a UX
one. At N=1 the ambiguity disappears.

The cap is written as **an MVP boundary tied to a named unknown, not a design
principle**. It moves to a stated numeric bound the moment the failed-member
representation is measured. The cap constrains nothing that ships, because no
alert verb is grantable in MVP.

### Q4: `report:run` ships shallow, `report:publish` defers

`report:run` ships with a fingerprint bound to definition **identity**. The
record states plainly, and the operator-facing summary must state, that the
check cannot detect content drift: definition content is largely carried by
referenced views that `GET /api/reportdefinitions/{id}` does not project, and
the 9.0.2 readback carries no version, timestamp, or content hash.

The reason of record for shipping is blast radius. A stale report definition
produces a wrong document, which is legible after the fact; nothing on the
monitored estate changes.

`report:publish` is deferred. `publish: true` is tenant-visible, an
outward-facing effect with an audience that confirmed nothing, and a shallow
fingerprint could publish unpreviewed content that cannot be recalled.
**`plan_mutation` refuses `publish: true` server-side in MVP**, rather than
merely leaving the scope ungranted, so the refusal does not depend on scope
configuration being correct.

### Alert ownership verbs are not implementable, not merely deferred

Raised by claude-worker in its ballot objections and adopted. Measured, no alert
of 1124 on DEVEL returns `ownerId` or `ownerName`, though the 9.1 schema
declares both. Whether ownership becomes readable once an alert is owned cannot
be determined without taking ownership, which is a mutation.

Under the settled rule that every family revalidates before apply,
`alert:takeownership`, `alert:releaseownership`, and `alert:assignownership`
have **no observable freshness signal and therefore cannot satisfy the gate**.
They are recorded as not implementable pending a Phase 2 gate measurement,
rather than sitting in a scope table implying they are merely unshipped.

### Scopes, per Scott's ruling 2

Derived from implemented capabilities, per-verb, default-deny. None granted in
MVP.

| Scope | Grantable when |
| --- | --- |
| `action:execute:<class>` | never before the Phase 2 gate, and not before Q2's populate question is answered |
| `alert:suspend` | when the alert_op adapter ships with the suspend verb registered |
| `alert:cancel` | same, **flagged wider blast radius**: cancel closes an alert outright |
| `alert:takeownership`, `alert:releaseownership`, `alert:assignownership` | not implementable until a freshness signal is confirmed to exist |
| `report:run` | when the report_run adapter ships |
| `report:publish` | deferred; refused server-side in MVP |

The grantable-scope registry is **derived at server start from the mutation
adapters actually registered**. The admin UI enumerates the registry. A scope no
registered adapter claims cannot appear in the UI and therefore cannot be
granted. This makes Scott's ruling 2 structural rather than a rule someone has
to remember.

### Read-only default, enablement toggle, prod hard block

The discriminator strengthens these, because they stop being keyed on the word
"action":

- `plan_mutation` refuses at plan time for a read-only target, for **every**
  value of `operation`. An alert verb against a read-only target never gets a
  plan, so it never reaches apply.
- The prod hard block is checked against **target identity**, not operation
  type, so a new `operation` value cannot route around it.
- **Structural enforcement, as a checkable invariant:** the adapter layer
  refuses any non-GET request to a VCF Ops target unless the calling frame
  carries a claimed plan token. This is testable by a unit test asserting no
  adapter method can issue a POST without a token, independent of any tool's
  code.

### Stale-denial rate

claude-worker asked for a threshold in the record now, arguing that setting one
later invites explaining the number away. It is right about the incentive and
the orchestrator has no data to pick a number honestly.

**Ruling:** the threshold is fixed as part of the Phase 2 gate, before any
mutation scope is granted, and **must be set without reference to the
then-observed rate**. That neutralizes the incentive claude-worker identified
without fabricating a number today.

## Escalated to the principal

**`docs/SPEC.md` section 4.1 contains a contract error.** It requires "alerts:
alerts, symptoms, acknowledge (acknowledge counts as an action for gating
purposes)". The VCF Ops API has no acknowledge verb: the string `acknowledg`
appears zero times in the 9.1 OpenAPI, and the real verb set is suspend, cancel,
takeownership, releaseownership, assignownership.

This is Scott's to resolve, not the team's, because `docs/SPEC.md` is the design
contract and a protected path, and because the plausible substitute changes the
blast radius. If "acknowledge" meant what a VCF Ops operator calls acknowledging,
the nearest verb is **`cancel`, which closes an alert outright**, and that is
materially wider than what SPEC's wording implies. The team did not guess.

Options for Scott, not ranked:

1. Amend SPEC to name `cancel` and accept the wider blast radius explicitly.
2. Amend SPEC to name the ownership verbs, which are the closer semantic match
   to "acknowledge" but currently have no observable freshness signal and so
   cannot satisfy the gate.
3. Amend SPEC to drop the alert mutation requirement from MVP, leaving alerts
   read-only.

No alert verb is grantable in MVP regardless, so this does not block the Phase 1
build.

## Division of labor

Prospective, for the Phase 1 build round. Assigned by capability.

| Piece | Assigned to | Why this harness |
| --- | --- | --- |
| Generic plan state machine, atomic claim, terminal states including the two new revalidation states | codex-worker | It designed the plan-as-security-boundary model and owns `outcome_unknown`. claude-worker explicitly declined this piece, arguing a new state belongs next to the machine it extends and that a seam between the two is where a stale plan slips through |
| Per-family precondition fingerprints and the revalidation adapter contract | claude-worker | It measured every field set in the table above, and record 001 already assigned it the catalog fingerprint that this generalizes. Splitting them would produce two canonicalization rules |
| Raw-byte payload digest and canonicalization versioning | codex-worker | It owns the digest contract, and the submitted-bytes ruling is a correction to its payload path that it should implement |
| Flat schema validation and cross-operation field rejection | agy-worker | Defensive JSON shaping against a bounded schema is its stated strength, and this piece is a refusal path with no mutation authority of its own |
| Grantable-scope registry derived from registered adapters | agy-worker | claude-worker explicitly handed this away as admin-UI-facing and store-facing rather than adapter-facing. It pairs with record 003's key-minting work |
| VCF Private AI Services render-and-validate test | claude-worker | It specified the normative/presentational split that the test result feeds |

claude-worker's declining of the plan state machine is recorded because it is
the kind of claim the orchestrator cannot write for a worker:

> I do not claim, and should not have, the plan store, the atomic claim, or the
> terminal-state machine. [...] Whoever owns `outcome_unknown` should own the
> two states adjacent to it, and that is codex-worker.

## Dissent

**agy-worker dissents on Q1**, quoted verbatim:

> Operators manage alert storms in batches. A hard cap of one destroys the
> primary workflow. A bounded batch with per-alert outcomes natively leverages
> the array returned by the API, serving the operator's intent while keeping
> revalidation time predictably within the apply deadline.

The orchestrator notes this dissent is about a capability that does not ship in
MVP, and that the decision above writes the cap as a boundary tied to a named
unknown precisely so agy-worker's workflow concern is answered the moment that
unknown is measured.

**codex-worker dissents on Q4a**, quoted verbatim:

> Identity and shallow metadata cannot detect a report definition's effective
> content changing behind referenced objects. Shipping with that known blind
> spot would label identity continuity as revalidation while allowing materially
> stale intent. Defer both `report:run` and `report:publish`; publishing is not
> a safer subset and has the wider tenant-visible effect. I would change to (a)
> if read-only evidence identifies a stable content or revision projection that
> binds the effective runnable definition.

The orchestrator ruled against this on blast radius: the failure mode of a
shallow report fingerprint is a wrong document, which is legible after the fact
and changes nothing on the monitored estate. codex-worker's rule is sound and
was written for operations that change estate state. The record's requirement
that the shallowness be stated in the operator-facing summary, not merely in the
record, is the concession to codex-worker's objection.

**No constitution-violation claims were raised this round.**

## Open risks carried forward

Named here so they are not rediscovered:

1. Whether `POST /api/actions/{id}/query` is side-effect-free and byte-stable.
   **Blocking for action apply.**
2. How a failed member of a bulk `POST /api/alerts` is represented. Blocking for
   any alert batch above N=1.
3. Whether `ownerId`/`ownerName` become readable once an alert is owned.
   Blocking for the three ownership verbs.
4. Whether VCF Private AI Services renders and validates the flat schema.
5. Whether any 9.0.x readback exposes report-definition content drift. Would
   remove the shallowness caveat and reopen codex-worker's dissent in its
   favour.

All five require either a mutation or a live client test, so all five belong to
the Phase 2 gate rather than to Phase 1.

## Protected paths touched

src/vcf_ops_mcp/

## Sign-offs

    Signed-off-by: claude-worker <claude@team.local> 2026-07-21T17:54:09Z
    Signed-off-by: codex-worker <codex@team.local> 2026-07-21T17:47:14Z
    Signed-off-by: agy-worker <agy@team.local> 2026-07-21T17:47:17Z

Transcribed by the orchestrator from each worker's own signature artifact,
because the records live on a branch the workers do not write to. The artifacts
are authoritative and independently checkable:

| Signer | Signature artifact | Commit |
| --- | --- | --- |
| claude-worker | `docs/history/signoffs/claude-worker-r2-records.md` | `a307102` |
| codex-worker | `docs/history/signoffs/codex-worker-r2-records.md` | `10c9282` |
| agy-worker | `docs/history/signoffs/agy-worker-r2-records.md` | `726daf4` |

Each signer confirms in its artifact that its own dissent, where it has one, is
quoted accurately and was not softened or truncated. All three signed without
withholding.

### Two defects claude-worker found in this record, and the corrections

Recorded rather than silently fixed, because the signature artifacts are
described above as the authoritative form and a reader should be able to see
what changed after they were written.

1. **An unmarked truncation of claude-worker's own concession.** The fresh-plan
   concession quoted in "Concessions" above originally stopped at "two
   paragraphs later." and dropped the closing clause without an elision mark.
   claude-worker flagged it in its signature, noting the cut removed a clause
   that made its own error look worse rather than better. The full sentence has
   been restored. No other quotation in this record is elided except the
   division-of-labor block, where the elision is marked `[...]`.

2. **The sign-off transcription would have failed the consensus gate.** The
   `Signed-off-by:` lines above initially carried a name and email but no
   timestamp, while `SIGNOFF_RE` in `tools/consensus-check.py` requires a
   trailing UTC ISO 8601 stamp, deliberately, because the stamp is what
   separates a real signature from the template placeholder. This record touches
   the protected path `src/vcf_ops_mcp/`, so the gate would have blocked the
   round PR. Timestamps were added from each signer's own `signed_at` field.

Both were found by the resident reviewing the record rather than by the
orchestrator that wrote it, which is the layer working as intended.
