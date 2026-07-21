# claude-worker, round 2, mutation gate amendment to record 001

- **Worker:** claude-worker
- **Branch:** `claude/r2-mutation-gate`
- **Base:** `round/1-architecture` at `a14b80f`
- **Written:** 2026-07-21T17:25:18Z
- **Phase:** 1, blind. No peer proposal read.

## Recon performed for this proposal

Read-only GETs against DEVEL (`vcf-lab-operations-devel.int.sentania.net`,
9.0.2) plus the vendor OpenAPI in `reference/docs/operations-api-9.1.json`.
No mutation of any kind was issued. No alert was acknowledged, no report was
run.

| Measurement | Value |
| --- | --- |
| `GET /api/alerts` `totalCount` | 1124 |
| `GET /api/reportdefinitions` `totalCount` | 74 |
| `GET /api/reports` `totalCount` (historical runs) | 1 |
| `GET /api/alerts/{id}` size / latency (3 samples) | 926 bytes, 29-38 ms |
| `GET /api/reportdefinitions/{id}` size / latency | 1661 bytes, 90-188 ms |
| `GET /api/resources/{id}` size / latency | 3010 bytes, 58-65 ms |
| Alert mutation endpoint | `POST /api/alerts?action=<verb>`, bulk over N alert IDs |
| Alert verbs named in the 9.1 spec | acknowledge, release, suspend (`minutes`), assignownership (`userAccountID`), and others |
| Report run endpoint | `POST /api/reports`, body `{resourceId, reportDefinitionId, traversalSpec, subject, publish}` |
| Report poll endpoint | `GET /api/reports/{id}`, carries `status` (observed `COMPLETED`) |

Three facts from this recon are load-bearing below and none of them were
available when record 001 was written:

1. **Alert acknowledgement is not an operation, it is a verb on a
   multi-verb endpoint.** `POST /api/alerts?action=` also accepts suspend,
   release, and assignownership. Any amendment that hardcodes "ack" names
   the wrong unit and will need re-amending the first time someone wants
   suspend.
2. **The alert endpoint is bulk.** It takes a list of alert IDs. One
   mutation call can move N alerts, which means partial success is
   reachable, and record 001's terminal-state vocabulary has no word for
   it. See risk 1.
3. **Alerts carry their own freshness fields.** `status`, `controlState`,
   `updateTimeUTC`, `cancelTimeUTC`. The single alert I sampled is
   `status: CANCELED` with `controlState: OPEN`, which is exactly the
   stale-plan case defect 2 describes: plan an ack, someone else cancels
   the alert, apply anyway.

---

## 1. Approach

### The short version

Neither of the review's two candidates as stated. **One gate, one plan
record, one pair of mutation tools, with a family adapter interface
underneath.** This is closer to the review's "generalized operation type"
than to "dedicated paths per family", but the load-bearing part is not the
discriminator, it is the adapter contract that every family must satisfy to
be reachable at all. That contract is what makes the gate structural rather
than a convention three code paths agree to follow.

I reject dedicated per-family plan/apply paths for one reason: a security
gate implemented three times is a gate that is correct in at most one place.
Record 001 already says "the security boundary is the plan record, not the
tool schema". Three plan records is three boundaries, and the read-only
check, the prod hard block, the atomic one-use claim, the expiry, and the
scope intersection would each get written three times by three residents on
three branches. The failure mode is not hypothetical: it is the same shape
as defect 1 itself, which happened because the action family got a gate and
the other two families got nothing.

I also decline the pure "generalized operation type with a payload
fingerprint" as the review phrased it, because a payload fingerprint alone
does not fix defect 2. Hashing the outbound payload proves the client did
not tamper with it. That is precisely the property codex-worker's round 1
critique already showed is insufficient ("a body hash proves only the client
did not alter the plan"). The payload digest and the freshness check are two
different fields doing two different jobs, and collapsing them is how defect
2 got introduced in the first place.

### Amended plan record

Record 001's plan record field list is replaced with this. Fields marked
**(unchanged)** carry over from record 001 verbatim and are listed only so
the amended record is readable standalone.

| Field | Purpose |
| --- | --- |
| `plan_id` | random, one-use **(unchanged)** |
| `key_id` | minting key identity **(unchanged)** |
| `target_id` | registered target **(unchanged)** |
| `target_posture` | snapshot of read-only / actions-enabled at plan time **(unchanged)** |
| `expiry` | **(unchanged)** |
| `operation` | **new.** Discriminator, one of `action`, `alert_op`, `report_run` |
| `subject_ref` | **new.** Family-specific, structured, opaque to the gate |
| `payload_digest` | **replaces** "normalized parameter digest". SHA-256 over the canonicalized request the server will actually send: method, path, sorted query string, and canonical-JSON body |
| `precondition_fingerprint` | **replaces** "definition fingerprint". Per-family digest over the upstream state whose change would alter what the operation means |
| `scope_required` | **new.** The action-class scope string, checked at plan and again at apply |
| `revalidation_policy` | **new.** MVP value is `strict` and it is the only implemented value |

`operation` is a closed enum. Adding a value is a decision-record change,
not a code change, which is what keeps a fourth mutation family from
arriving unrecorded the way alerts and reports did.

`subject_ref` per family:

- `action`: `{action_id, context_resource_ids}`
- `alert_op`: `{verb, alert_ids}`
- `report_run`: `{report_definition_id, resource_id, traversal_spec, subject, publish}`

`revalidation_policy` exists as a field with exactly one legal value on
purpose. It gives a future relaxation somewhere to be recorded instead of
being a quiet edit to a conditional.

### What replaces the definition fingerprint

`precondition_fingerprint` is a SHA-256 over a canonical serialization of a
per-family field set. The field sets are the substance of this proposal and
should be in the record as a table, because "fingerprint the relevant state"
is not implementable and this is:

| Family | Fields hashed | Source call |
| --- | --- | --- |
| `action` | the single action definition record plus its `contextResourceKindKey`, plus the parameter set and populated defaults returned by populate for the named `contextResourceId` | `GET /api/actiondefinitions` (cached, per record 001) plus the populate call |
| `alert_op` | per alert ID: `alertId`, `status`, `controlState`, `updateTimeUTC`, `cancelTimeUTC`, `alertDefinitionId`, `resourceId` | `GET /api/alerts/{id}` |
| `report_run` | report definition `id`, `name`, `subject`, `traversal-specs`, plus the context resource's `identifier` and `resourceKey.resourceKindKey` | `GET /api/reportdefinitions/{id}` plus `GET /api/resources/{id}` |

The action row is record 001's per-definition fingerprint (the C1 graft)
plus the populate output. Adding populate output is not decoration: it is
the direct fix for defect 2's observation that the catalog record is
documented as carrying no parameter metadata, so a catalog-only fingerprint
cannot detect a defaults change. Record 001's fingerprint was hashing the
one object guaranteed not to contain the thing that drifts.

### Revalidation, concretely, per family

Position in the sequence: inside the atomic plan claim, after every
authorization predicate has passed, before any outbound mutation is
composed. Recompute `precondition_fingerprint` from live data and compare
to the stored value.

| Family | Revalidation call(s) | Measured cost on DEVEL |
| --- | --- | --- |
| `action` | re-run populate, then validate, for the plan's `contextResourceId` | not measured, 2 calls |
| `alert_op` | `GET /api/alerts/{id}` for the single planned alert | 926 bytes, 29-38 ms |
| `report_run` | `GET /api/reportdefinitions/{id}` and `GET /api/resources/{id}` | 4671 bytes, 148-253 ms combined |

Added apply latency is 30 ms to roughly 250 ms for the two families I could
measure. That is the entire cost of defect 2. I want that number in the
record, because "revalidate before applying" reads expensive in the abstract
and is not, and the next resident to consider dropping it should have to
argue against a measurement rather than an intuition.

### Failure states, and where the two defects decouple

Scott's dispatch asks whether the two defects are separable. They are
coupled at the plan record and **separable at the failure model**, and I
think that is the sharpest thing here.

Revalidation runs entirely before submission. `outcome_unknown` is by record
001's own definition the state of a consumed plan whose *upstream submission*
timed out. A revalidation failure happens before anything was submitted, so
it can never be `outcome_unknown`, and the two cannot overlap. Two new
terminal states, both non-mutating:

- **`revalidation_changed`**: preconditions moved. Plan is consumed. No
  mutation submitted. Response carries `changed_fields` naming what moved,
  so the client can tell the operator "this alert was canceled by someone
  else since you planned it" rather than "denied".
- **`revalidation_unavailable`**: the revalidation call errored or timed
  out. Plan is consumed. No mutation submitted. **Never fail open**, and
  never retry automatically, on the same reasoning record 001 already
  accepted for submission timeouts.

The plan is consumed in both cases. Record 001 says claim atomically, then
recheck, and that ordering is right: it is the only ordering that keeps the
one-use property under concurrent applies. Burning a plan on a failed
revalidation is cheap, because re-planning is one tool call.

### Changed means a new plan, not an error

`apply_mutation` on `revalidation_changed` returns the denial **and a freshly
issued plan** for the same intent, in one response, with the diff. The
operator sees what moved and confirms once. The replacement plan carries no
special standing: it goes through the identical apply gate, with its own
scope check, posture check, expiry, and revalidation. This is a round-trip
saving, not a gate weakening, and the record should say so in those words so
nobody later implements it as auto-continue.

### Tool surface: still six, three renamed, zero added

Record 001's reasoning was about what a tool-calling-only client such as VCF
Private AI Services can carry. That reasoning binds, so the mutation surface
does not grow.

| Record 001 | Amended | Change |
| --- | --- | --- |
| `list_action_definitions` | `list_action_definitions` | none |
| `populate_action` | `populate_action` | none, stays action-only |
| `validate_action` | `validate_action` | none, stays action-only |
| `plan_action` | `plan_mutation(target_id, operation, subject)` | renamed, generalized |
| `apply_action` | `apply_mutation(plan_id, plan_token)` | renamed |
| `get_action_task` | `get_mutation_status(target_id, handle)` | renamed, generalized |

Signatures:

```
plan_mutation(target_id: str, operation: "action"|"alert_op"|"report_run",
              subject: object) -> Plan | StructuredDenial
apply_mutation(target_id: str, plan_id: str, plan_token: str)
              -> Result | StructuredDenial
get_mutation_status(target_id: str, handle: str) -> Status
```

Three points a critic should push on, so I will state them first:

- **Why rename at all.** Because keeping the name `apply_action` for a tool
  that acknowledges alerts is the exact naming lie that produced defect 1.
  The names are free to fix today and expensive to fix once anything
  depends on them. No production code has shipped.
- **Why `populate` and `validate` stay action-only.** Alerts and reports
  have no populate step. Generalizing tools that only one family uses buys
  symmetry and costs honesty.
- **Why the surface does not need `list_alerts_for_ack` or
  `list_runnable_reports`.** Discovery for both families is already carried
  by read tools the read surface must ship anyway (the alerts family and
  the reports family in SPEC 4.1). The mutation surface consumes IDs those
  tools already return. This is why generalizing costs zero tools while
  dedicated per-family paths would cost four.

`get_mutation_status` generalizes cleanly because all three families are
pollable or trivially terminal: actions return a task ID, report runs return
a report ID whose `GET /api/reports/{id}` carries `status`, and alert ops
complete synchronously and return a terminal status immediately.

### Read-only default, enablement toggle, prod hard block

The discriminator makes these stronger, not weaker, because they stop being
keyed on the word "action".

- `plan_mutation` refuses at plan time for a read-only target, for **every**
  value of `operation`. An alert acknowledgement against a read-only target
  never gets a plan, so it never reaches apply.
- The prod hard block is checked against **target identity**, not operation
  type, so a new `operation` value cannot accidentally route around it.
- **Structural enforcement, stated as a checkable invariant:** the adapter
  layer refuses any non-GET request to a VCF Ops target unless the calling
  frame carries a claimed plan token. That is the sentence that makes "an
  alert ack against a read-only target must refuse server-side" testable
  rather than aspirational, and it is testable by a unit test that asserts
  no adapter method can issue a POST without a token, independent of any
  tool's code.

### Scopes, per Scott's ruling 2

New capabilities, their scope names, and what makes each grantable:

| Scope | Capability | Grantable when |
| --- | --- | --- |
| `action:execute:<class>` | action framework execute | never before Scott's Phase 2 gate, per record 001 |
| `alert:acknowledge` | `POST /api/alerts?action=acknowledge` | when the alert_op adapter ships with the acknowledge verb registered |
| `report:run` | `POST /api/reports` with `publish: false` | when the report_run adapter ships |
| `report:publish` | `POST /api/reports` with `publish: true` | when the publish path ships, separately from `report:run` |

Two notes. First, `report:publish` is split from `report:run` because
`publish: true` makes a report tenant-visible, which is a wider blast radius
than generating one, and that split came out of reading the request schema
rather than out of a guess. Second, the other alert verbs the 9.1 spec names
(`alert:suspend`, `alert:release`, `alert:assign_ownership`) are deliberately
named here and deliberately **not** implemented in MVP, so per ruling 2 they
are not grantable. Naming them costs nothing and stops the next resident
from inventing a different scope vocabulary.

Ruling 2 becomes structural rather than a policy anyone has to remember: the
grantable-scope registry is derived at server start from the mutation
adapters actually registered. The admin UI enumerates the registry. A scope
name no registered adapter claims cannot appear in the UI, so it cannot be
granted, so minting `read_logs` when no `read_logs` capability exists is not
a rule that can be broken by forgetting it.

---

## 2. Risks

Ordered by how much damage they do to my own proposal.

**1. Bulk alert operations break the terminal-state model, and I do not fix
it.** `POST /api/alerts?action=` takes a list. Ten alerts can come back as
seven acknowledged and three failed. Record 001's terminal states are
whole-plan states and have no vocabulary for partial. My amendment inherits
that gap and papers over it by capping MVP at **one alert ID per plan**,
which I would put in the record explicitly. That cap is a real usability
cost (an operator clearing twelve alerts does twelve plan-apply round trips
through a plan gate) and it is a deferral, not a solution. Partial success
is reachable for multi-resource actions too. If a peer has a better answer
than a cap, I would rather take theirs.

**2. I could not verify the alert mutation response shape, because verifying
it would mean acknowledging a real alert.** Everything I say about
`alert_op` returning a terminal status synchronously is inferred from the
OpenAPI, not observed. If `POST /api/alerts?action=acknowledge` returns 200
with an empty body, my "did it actually work" story for alerts is materially
weaker than the action family's task-poll story, and `get_mutation_status`
would have to fall back to re-reading `GET /api/alerts/{id}` and inferring
success from `status`. That fallback is inference, not confirmation.

**3. Revalidating actions by re-running populate assumes populate is
idempotent, and I have not proven it.** It is a POST. If it allocates
anything server-side, or if it is rate-limited, then revalidation-by-
repopulate is unsafe and the action row of my fingerprint table needs a
different source. **Given one hour and one question against DEVEL, this is
what I would ask:** does calling populate twice for the same action ID and
resource ID return byte-identical parameter output and leave no server-side
artifact? It is the assumption most likely to be quietly wrong, and it sits
under the family with the largest blast radius.

**4. One generalized gate is one place to get it wrong.** A discriminator
dispatch bug is wrong for all three families simultaneously, where dedicated
per-family paths fail independently. I judge that one gate reviewed hard
beats three gates reviewed once, and that the shared-predicate duplication
in the per-family design is the larger risk. But that is a judgment about
review quality, not a proof, and a reviewer could reasonably invert it. If
someone argues the inverse, the strongest form of their argument is that the
three families have genuinely different async models, and my
`get_mutation_status` generalization is the seam where that difference will
show.

**5. Canonicalizing `traversal_spec` for the payload digest is where digest
bugs hide.** It is a nested object, the 74 report definitions carry many
distinct traversal specs, and key ordering, absent versus null, and
whitespace all have to be pinned. A digest that is unstable across two
serializations of the same intent produces spurious `revalidation_changed`
denials, which is the exact "recurring false refusals train operators to
stop trusting the check" failure I raised against codex-worker in round 1.
I would be applying my own C1 critique to my own design here.

**6. Renaming three tools costs a documentation delta.** Record 001, SPEC
4.1, and anything else naming `plan_action` all go stale together, and
somebody will read a stale mention. Cheap now, not free, and worth doing
only because nothing depends on the names yet.

**7. The report family's freshness question may be the wrong question.**
Report definitions on a lab appliance change rarely (74 of them, largely
stock). Fingerprinting them may be near-pure overhead, while the thing that
actually drifts is the context resource. If so, the report row of my table
is two calls where one would do, and the honest fix is to drop the
definition from the fingerprint and keep only the resource. I left both in
because I would rather be caught over-checking than under-checking on the
defect the review just opened, but I do not have data showing definition
drift matters.

---

## 3. Division-of-labor claim

**I claim the per-family precondition fingerprint definitions and the
revalidation adapter contract.**

Two reasons, and neither is "I would enjoy it". Record 001 already assigned
me the catalog cache, TTL, per-definition fingerprint, and refresh rate
limiting, on the grounds that my C1 and C4 critiques were the specification
for that piece. What I am proposing is the direct generalization of exactly
that piece: the fingerprint stops being action-shaped and becomes a
per-family contract. Splitting it from the work already assigned to me would
put the action fingerprint and the alert and report fingerprints in two
different heads, which is how they end up with two different canonicalization
rules and risk 5 becomes real. Second, the field lists in my table came from
recon I did for this proposal, so I am carrying the measurements the
implementation needs.

**I do not claim, and should not have, the plan store, the atomic claim, or
the terminal-state machine.** Record 001 assigned those to codex-worker
because it designed the plan-as-security-boundary model, and my amendment
adds two states (`revalidation_changed`, `revalidation_unavailable`) to a
state machine it owns. A new state belongs next to the machine it extends.
If my failure-model change and codex-worker's `outcome_unknown` land on two
branches, the seam between them is precisely where a stale plan slips
through, which is the defect we are here to close. Whoever owns
`outcome_unknown` should own the two states adjacent to it, and that is
codex-worker.

The piece I would actively hand elsewhere is the **scope registry derived
from registered adapters**, the mechanism that makes ruling 2 structural.
That is admin-UI-facing and store-facing rather than adapter-facing, it
touches the credential store design in record 003, and it wants whoever owns
key minting. It is not mine and I would rather say so than collect it.

---

## 4. Rough estimate

**The record amendment itself: half a day of one worker.** It is a field
table, a per-family fingerprint table, a failure-state section, a scope
table, and a tool-rename delta. The substance is already in this proposal
and in the two peer proposals I have not read.

**The Phase 1 implementation this amendment specifies: two to three days
across the three residents**, dominated by the plan store and the atomic
claim, which record 001 had already scoped. Generalizing the fingerprint
adds maybe half a day over the action-only version, because the two new
families are one and two GETs respectively and neither needs a cache.

What blows this up, in order:

- **Risk 3 coming back badly.** If populate is not idempotent, the action
  family needs a different revalidation source, and that is a change to the
  shape of the record rather than an edit to it. Second round.
- **Risk 1 not being deferrable.** If Scott or a peer rejects the one-alert-
  per-plan cap, partial-success semantics have to be designed for all three
  families, and that is a genuinely hard state-machine problem worth more
  than everything else in this amendment combined.
- **Risk 2 turning out badly.** A silent alert mutation response means
  designing a confirmation story from inference, which is unpleasant and
  slow, and cannot be validated at all before the Phase 2 gate lets anyone
  mutate anything.

Everything else on the risk list is hours, not days.
