# claude-worker, round 2, phase 2 adversarial critique

- **Worker:** claude-worker
- **Branch:** `claude/r2-mutation-gate`
- **Written:** 2026-07-21T17:32:46Z
- **Proposals read:** codex-worker `63567bf8`, agy-worker `a08f6ae0`, own `ce6e6c05`
- **Recon performed for this critique:** yes, read-only GETs against DEVEL
  (9.0.2, `versions/current` confirms `VCF Operations 9.0.2.0`, build 25137838)
  plus the vendor OpenAPI at
  `vcf-content-factory/reference/docs/operations-api-9.1.json`. No POST of any
  kind was issued against any appliance. Full numbers in section 4.

The single most consequential thing this round produced is not in any of the
three proposals: **the VCF Ops API has no alert acknowledgement operation.**
Two of the three proposals are built on one. That is section 1 of both
critiques and section 2 of my concessions, because I named a nonexistent verb
too.

---

## 1a. Critique of agy-worker's proposal (`a08f6ae0`)

### Strongest objection: all three revalidation calls are wrong, and two of them are to things that do not exist

agy's proposal is a revalidation design. Its section on "Revalidation
immediately before apply" is the load-bearing part, and each of its three rows
is falsified by the spec or by DEVEL.

**`report_run`.** agy specifies `GET /api/reports/{operation_id}` to read "the
report definition's modification timestamp". Two independent errors:

1. `/api/reports` is the report *run* collection, not the definition
   collection. Measured on DEVEL, passing a report-definition ID to it:

   ```
   GET /suite-api/api/reports/81f0f059-145d-4bce-bf3d-65447d2048f0
   HTTP=404  {"type":"Error","message":"No such Report - 81f0f059-...","apiErrorCode":404}
   ```

   The definition read is `GET /api/reportdefinitions/{id}`, which returns 200
   at 1661 bytes for the same ID.

2. There is no modification timestamp on the correct endpoint either. Measured,
   `GET /api/reportdefinitions/{id}` on 9.0.2 returns exactly
   `['active','description','id','links','name','owner','subject','traversal-specs']`.
   No `creationTime`, no `lastRunTime`, no modification time. The 9.1 schema
   declares `creationTime` and `lastRunTime`; 9.0.2 does not return them, and
   neither version declares a modification time. agy's report fingerprint hashes
   a field that does not exist on an endpoint that returns 404.

**`action`.** agy specifies "re-run `POST .../validate` with the planned
payload". There is no action validation endpoint. The entire action surface in
the 9.1 spec is four operations: `GET /api/actiondefinitions`,
`POST /api/actions/{id}/query` (operationId `populateAction`),
`POST /api/actions/{id}` (operationId `performAction`), and
`GET /api/actions/{taskId}/status`. The only path in the whole spec matching
`valid` is `/api/fleet-management/iam/saml-metadata/validate`, which is
unrelated. So agy's action revalidation, its "one extra API call", and its
`Action Validation Latency` risk are all about a call that is not there. The
only substitute is populate, which is a POST, which is precisely the
idempotency worry agy's own closing paragraph says would require "a completely
different state-comparison approach". agy's proposal therefore already contains
its own defeat; it just does not know the trigger condition is unconditionally
true.

**`alert_ack`.** agy fingerprints `status` and `cancelTime`, and fails
revalidation "if the alert is no longer ACTIVE (for example, already canceled
or acknowledged)". Measured over all 1124 alerts on DEVEL:

| Field | Distribution |
| --- | --- |
| `status` | 1086 `CANCELED`, 38 `ACTIVE` |
| `controlState` | 1124 `OPEN`, 0 anything else |

`status` is the field the `cancel` verb moves. The acknowledgement-analogue
verbs the API actually has (`takeownership`, `releaseownership`,
`assignownership`) act on ownership, and `suspend` acts on
`suspendUntilTimeUTC`. So for every verb except cancel, agy's fingerprint reads
a field the operation does not touch and is blind to the drift that actually
matters, which is another operator taking ownership between plan and apply.
The freshness check watches the wrong field for the operation it names.

**What would change my mind:** a 9.0.x action validation endpoint I missed
(I searched the 9.1 spec's full path list), or a report-definition readback
that carries a modification time, or an alert field on 9.0.2 that carries
acknowledgement or ownership state. I checked for the last one and DEVEL
returns no owner field on any of 1124 alerts; see the open risk in 1b.

### 2. `stale_plan` does not say the plan is consumed, which leaves a spin-until-you-win hole

agy's failure states say a stale plan "is rejected with a structured
`stale_plan` error" and "the operator must explicitly call `plan_mutation`
again". It never says the plan transitions to a terminal state. If a rejected
plan stays claimable, a client holding a valid token can retry apply in a loop
against a flapping subject until the fingerprint momentarily matches, and the
apply that eventually lands is the one the operator confirmed against a state
that had already moved and moved back. That is the defect the freshness check
exists to close, reintroduced through the retry path. Both codex and I consume
the plan on every apply attempt including failed ones. agy is the only proposal
that does not say so.

**What would change my mind:** agy stating that apply atomically claims the
plan before revalidation and that every outcome, including `stale_plan` and
`revalidation_timeout`, is terminal. I expect this is what agy meant, but a
gate is what the record says, not what the author meant.

### 3. Read-only default and the prod block are asserted, not mechanised

agy writes that "the read-only default and prod hard-block apply identically;
`apply_mutation` asserts the target's enablement flag before revalidation
regardless of `operation_class`." That is a statement that the code will do the
right thing. It names no enforcement point below the tool layer, and it puts
the only stated check at apply, with nothing at plan time. Under agy's design a
read-only target still mints plans, so the refusal depends entirely on one
conditional in one function being present and correct. This is the weakest of
the three on the invariant CLAUDE.md calls structural: "a read-only target's
action-execution paths refuse server-side, regardless of what any client asks
for."

**What would change my mind:** a named invariant below the tool layer that a
test can assert without going through `apply_mutation`. Mine is that no adapter
method may issue a non-GET without a claimed plan token; codex's is the
equivalent claim that gating alert and report operations as mutations makes the
toggle and prod refusal structural. Any of the three shapes works. Asserting
the outcome does not.

### 4. The proposal prices nothing and measures nothing

agy's risk 1 asserts action validation is "heavyweight" and could hit the HTTP
timeout. My measurements say the two revalidation families I can read cost 30ms
(alert detail, 926 bytes) and roughly 150 to 250ms (report definition plus
resource). agy's own hourly DEVEL question, whether `updateTime` changes on a
duplicate symptom trigger, is a good question, and it is answerable from the
data agy did not gather: on DEVEL, `updateTimeUTC` equals `startTimeUTC` on the
sampled alert and 1086 of 1124 alerts are already terminal, so the flap-rate
worry is real but unquantified in the proposal. This objection is the weakest
of the four and I raise it only because agy's latency risk is the one place the
proposal argues *against* a safety check, and it argues on an unmeasured
intuition.

**What would change my mind:** a measurement showing any revalidation read on
DEVEL above about a second.

---

## 1b. Critique of codex-worker's proposal (`63567bf8`)

codex's proposal is the strongest of the three on the state machine, and my
objections are narrower than they are for agy. That is not a courtesy; two of
them are still holes.

### Strongest objection: "never blindly the stored bytes" contradicts codex's own confirmation argument, and opens a canonicalization gap

codex's action preflight says: "The submit payload is the newly validated
effective payload, never blindly the stored bytes." Elsewhere codex argues
against handing back a fresh plan on staleness because "confirmation belongs to
the exact summary and payload the operator saw."

Both cannot be load-bearing. If the submitted payload is recomputed at apply
time, the bytes that reach VCF Ops are not the bytes the operator saw; they are
bytes that hash equal under a server-owned canonicalization to the ones the
operator saw. codex closes most of the gap by refusing on any changed effective
payload digest, but that makes the recomputation buy nothing over submitting
the stored bytes, while leaving the residue: canonicalization is by definition
lossy relative to raw bytes. Key ordering, absent versus explicit null,
numeric formatting, and whitespace are exactly the dimensions a canonicaliser
normalises away, and any of them can differ between the stored payload and the
recomputed one while the digest matches. codex names canonicalization as
"versioned and server-owned" but never says the digest is over raw bytes, so
the difference is unbounded in the dimensions the canonicaliser folds.

The safe form is the one codex rejects: submit the stored bytes, and use the
recomputed payload only as a comparison input to the refusal decision. That
preserves codex's own confirmation principle exactly, and I would rather codex
apply its principle to its own payload path than only to my fresh-plan
proposal.

**What would change my mind:** codex specifying that `effective_payload_digest`
is computed over the raw serialized request bytes rather than a canonical
projection, or that the operator-facing summary is regenerated from the bytes
actually submitted. Either closes it.

### 2. `alert_ack` names an operation the API does not have, and the real verb set includes `cancel`

The documented description of `POST /api/alerts` in the 9.1 spec, verbatim:

> Modify multiple Alerts by looking them up using their identifiers and
> performing one of the following actions - *Suspend*, *Cancel*, *Take
> Ownership*, *Release Ownership*

with query examples `action=suspend&minutes=1`, `action=cancel`,
`action=takeownership`, `action=releaseownership`, `action=assignownership`.
The string `acknowledg` appears **zero times** in the entire 9.1 OpenAPI
document (I grepped case-insensitively across the raw file).

This lands on codex harder than the naming point alone. codex's alert preflight
requires each alert to "remain acknowledgeable and unacknowledged" and its
fingerprint includes "current acknowledgement state". There is no such state to
read. Measured on DEVEL, the alert record exposes exactly
`alertDefinitionId, alertDefinitionName, alertId, alertImpact, alertLevel,
cancelTimeUTC, controlState, resourceId, startTimeUTC, status, subType,
suspendUntilTimeUTC, type` and nothing else, identically from the collection
and the `{id}` detail read. So codex's alert preflight predicate has no field
to evaluate.

Worse for the scope model: the verb set includes `cancel`, which closes an
alert, and `assignownership`, which takes a `userAccountID` and reassigns work
to a named human. Both are materially wider blast radius than an
acknowledgement, and `mutate.alert_ack` as a single grantable scope would carry
them if the adapter is written to the endpoint rather than to the verb. Under
Scott's ruling 2 the scope must be derived from the implemented capability, and
the implemented capability here is a verb, not the endpoint. codex's scope
vocabulary needs to be re-cut per verb.

**What would change my mind:** a field on 9.0.2 alerts carrying acknowledgement
state. I looked: the 9.1 schema declares `ownerId` and `ownerName`, and DEVEL
returned neither on any of 1124 alerts, all of which are unowned
(`controlState` is `OPEN` for all 1124). Whether ownership becomes readable
once an alert is owned cannot be settled without taking ownership of a real
alert, which is a mutation, so per Scott's constraint **this stays an open risk
in the record**: the freshness signal for the ownership verbs may not be
observable at all, and if it is not, those verbs cannot be revalidated and
should not ship.

### 3. codex prices a validation call that does not exist, and never asks about the one that does

codex writes that apply costs "roughly two to three upstream calls for an
action (definition read, populate, validation)" and hedges with "call the VCF
Ops validation operation where available", plus the good line that "lack of
such an endpoint must not be disguised as validation". The hedge means this is
not a false claim. It is still a cost that is not there, under a 5 to 8
engineer-day estimate partly built on it.

The substantive part is what the hedge silently does. With no validation
endpoint, codex's action preflight degrades to definition read plus populate,
which makes populate the sole revalidation source for the highest blast radius
family. `POST /api/actions/{id}/query` is a POST. codex's list of DEVEL
questions is thorough on alert and report contract shape and never asks whether
populate is side-effect-free. That is the one assumption codex's own action
preflight cannot survive being wrong about, and it is the only proposal-level
gap where codex is less careful than agy, whose closing paragraph flags the
same worry (about the wrong endpoint, but flags it).

**What would change my mind:** an action validation operation in 9.0.x that I
failed to find.

### 4. codex's own rule, applied to codex's report family, says report_run should not ship yet

codex writes: "A definition family without a safe detail/readback contract does
not implement `report_run` and its scope cannot be granted." Good rule. Now
measure the readback. `GET /api/reportdefinitions/{id}` on 9.0.2 returns
`active, description, id, links, name, owner, subject, traversal-specs`. There
is no version, no timestamp, and no content hash. A definition whose *content*
changes without changing name, subject, traversal-specs, or active is
indistinguishable across a plan boundary, and definition content in VCF Ops is
largely carried by referenced views, which this endpoint does not project at
all. codex's report fingerprint can therefore only detect the shallowest class
of drift.

So codex must either apply its own rule and defer `report_run`, or say plainly
that the report fingerprint is shallow and bound to definition identity rather
than definition content. I would take the second. I flag it because codex wrote
the rule that forbids the first option's opposite, and a rule a proposal states
and then does not apply to itself is worth more to surface than a rule it never
stated. Note this hits my proposal identically, and I say so in section 2.

**What would change my mind:** a 9.0.2 readback exposing report-definition
content drift. I did not find one.

### 5. Claim-before-preflight plus no-fresh-plan compounds into an operator-trust cost codex defers measuring

codex accepts that claim-before-preflight lets transient read failures consume
plans, and separately refuses to return a replacement plan. Individually both
are defensible and I now agree with the second (section 3). Combined, a flapping
subject or a flaky read means the operator does N plan-then-apply round trips,
each burning a plan. codex's answer is "strict refusal first, with later
field-specific stability rules only after measured evidence". That defers the
exact measurement that decides whether the design is usable, and in round 1 I
argued against codex that recurring false refusals train operators to stop
reading refusals. codex's proposal now contains the mechanism I warned about
and postpones the evidence.

This is my weakest objection against codex, because "measure it later" is a
reasonable answer to a question that cannot be measured before Phase 2.

**What would change my mind:** codex naming a threshold in the record now, for
example that a stale-denial rate above some fraction of applies is treated as a
design defect rather than as the gate working. A number in the record before
anyone has an incentive to explain the number away.

### 6. On the union, pressing where codex invited it

codex flags that a tool-calling-only client may render discriminated unions
poorly and offers typed planners plus one generic `apply_mutation` as the
fallback. I think the fallback is backwards. Plan time is where the posture
snapshot, the scope resolution, and both fingerprints are computed. Splitting
`plan_mutation` into three typed planners duplicates the half of the gate that
has the security content and shares only the half that is a state transition,
which is the inverse of the correct split.

If the union really is a client problem, the right answer is to flatten rather
than to fork: keep one `plan_mutation(target_id, operation, ...)` whose
remaining parameters are a small flat set of optional scalars and string arrays
(`action_id`, `resource_ids`, `alert_ids`, `verb`, `report_definition_id`,
`parameters`), with the server rejecting any field not belonging to the named
operation. Flat optional scalars are the shape such clients render most
reliably, and the rejection rule keeps the discriminator closed. This costs
zero tools and duplicates no gate.

I raise it against codex only because codex raised it. It defeats my own
signature harder: my `subject: object` is an opaque nested object, which is the
worst of the three shapes for a client that struggles with unions. See section
2.

---

## 2. Concessions

**To codex-worker and agy-worker, on point 1, the fresh plan in the denial.
They are right and I was wrong.** My proposal said a `revalidation_changed`
denial should carry a freshly issued plan for the same intent, and I argued it
changes no gate property because the replacement goes through the identical
checks. The server-side half of that is true and it is not the half that
matters. The consumer of that response is usually an LLM client with a goal to
complete, and I would be handing it a `plan_id` and a `plan_token` in the same
payload as the denial. It can call apply immediately, and it will, and no human
will have seen the new summary. I described the thing I must not build and then
described the mechanism for building it two paragraphs later, in the same
document where I insisted the record say "so nobody later implements it as
auto-continue". codex put it better than I can: confirmation belongs to the
exact summary and payload the operator saw. A denial may carry the diff and the
changed fields. It must not carry a usable token.

**To agy-worker, on `GET /api/reports/{id}` for report status.** agy's polling
model and my own both use `/api/reports/{id}`, and my proposal's report row is
right only because I used `/api/reportdefinitions/{id}` for the definition. I
had both endpoints in my recon table and did not state the distinction as a
trap. agy fell into it; my document did nothing to stop that, and the two paths
differing by one word is worth an explicit line in the amended record.

**To codex-worker, on per-alert outcomes versus my cap.** I proposed capping
MVP at one alert per plan and called it a deferral rather than a solution.
codex proposed per-alert outcomes in the plan and audit model with no automatic
whole-batch retry. codex's is better and it is also cheaper than I assumed: the
documented 200 response to `POST /api/alerts` is an `alerts` array of per-alert
records keyed by `alertId`, so per-alert readback is the endpoint's native
response shape, not something we have to reconstruct. My cap was solving a
problem the response body already half solves. I withdraw the cap in favour of a
bounded batch with per-alert outcomes derived from that array. What remains
genuinely unknown is how a *failed* member of the batch is represented, since
the documented example shows only successes, and that cannot be settled without
mutating. It stays an open risk.

**To codex-worker, on typed status projection.** codex is right that
`get_mutation_status` cannot assume every family returns an actions task ID. I
asserted the generalization was clean; codex is more careful. Confirmed: the
documented 201 for `POST /api/reports` returns a `report` object carrying
`status`, `completionTime`, and `id`, not a task ID, and the actions family
returns a `taskId` polled at a different path. Same tool, three different
handle types. codex's insistence on a typed projection rather than a shared
assumption is correct and my proposal was loose there.

**To codex-worker, on the tool schema for a tool-calling-only client.** codex
was the only one of the three to flag that the union may be a client problem.
My proposal's `plan_mutation(target_id, operation, subject: object)` passes an
opaque nested object, which is worse than codex's typed union branches for
exactly the client codex is worried about, and I did not notice. My section 1b
objection 6 is a flattening proposal, not a defence of what I wrote.

**About my own recon, unprompted by any peer.** My proposal listed the alert
verbs as "acknowledge, release, suspend (`minutes`), assignownership". The
actual documented set is suspend, cancel, takeownership, releaseownership,
assignownership. There is no `acknowledge` verb and no `release` verb.
My scope table's `alert:acknowledge` maps to
`POST /api/alerts?action=acknowledge`, which is a request the appliance will
not honour. I got the structural claim right, that the unit is a verb on a
multi-verb endpoint, and I got the verb list wrong while presenting it as
recon. The structural claim survives and is in fact stronger than I argued:
the real verb set contains `cancel`, which closes an alert outright, so
"the alert unit is an ack" is not merely imprecise, it understates the blast
radius by a lot.

---

## 3. Where I have changed my position

1. **Fresh plan on a failed revalidation: withdrawn.** A
   `revalidation_changed` denial carries the changed fields and a human-readable
   diff, and no `plan_id` and no `plan_token`. Re-planning is an explicit
   `plan_mutation` call by the client, and the operator confirms the new
   summary. This concedes the round's sharpest three-way split to codex and agy,
   and I ask that the record carry the reason in the form codex gave it rather
   than in the form of my retraction.

2. **One alert per plan: withdrawn**, in favour of a bounded batch with
   per-alert outcomes read back from the response's `alerts` array. The bound
   should be a number in the record, chosen so that per-alert revalidation reads
   stay inside the apply deadline. At 30ms per `GET /api/alerts/{id}` on DEVEL,
   a bound of 25 costs about 750ms of revalidation, which is the right order of
   magnitude to argue about.

3. **`alert_op` verb naming: changed and hardened.** My `subject_ref` for
   `alert_op` was `{verb, alert_ids}`, which is right, but my scope table named
   verbs that do not exist. The correct grantable scope set derived from the
   actual capability surface is `alert:suspend`, `alert:cancel`,
   `alert:takeownership`, `alert:releaseownership`, `alert:assignownership`,
   none of them granted in MVP, and `alert:cancel` and `alert:assignownership`
   flagged in the record as wider blast radius than the rest.

4. **The action revalidation source: downgraded from a claim to an open
   question.** My table said "re-run populate, then validate". There is no
   validate. That leaves populate, `POST /api/actions/{id}/query`, alone. Its
   operationId is `populateAction` and the spec describes it as a query that
   "would yield a response object", which is suggestive of read-only and is not
   proof. I did not call it, because calling a POST against a live appliance to
   find out whether POSTs are safe is the thing this round exists to prevent.
   Per Scott's constraint, this stays an open risk in the record, and it is the
   single highest-value question for the Phase 2 gate.

5. **`get_mutation_status`: from a generalization to a typed projection**, per
   codex. Three handle types, three status shapes, one tool.

6. **The union: not defended as written.** I now prefer the flat-optional-scalar
   form in 1b objection 6 over both my opaque `subject: object` and codex's
   nested union, and I would want it tested against VCF Private AI Services
   before the record commits.

What I have not changed: one gate rather than three, the adapter contract as
the structural enforcement point, plan-time refusal for read-only targets in
addition to apply-time, the prod block keyed on target identity rather than
operation type, and consuming the plan on every apply attempt.

---

## 4. New recon performed for this critique

All read-only. Appliance: `vcf-lab-operations-devel.int.sentania.net`, DEVEL
only, confirmed `VCF Operations 9.0.2.0` build 25137838 via
`GET /suite-api/api/versions/current`. No POST was issued to any appliance
other than `auth/token/acquire`. Nothing was run against prod. Spec reads are
against `vcf-content-factory/reference/docs/operations-api-9.1.json`.

| Question | Endpoint / source | Result |
| --- | --- | --- |
| Does an alert acknowledge verb exist? | 9.1 spec, case-insensitive grep for `acknowledg` across the whole document | **0 occurrences** |
| What verbs does the alert endpoint take? | 9.1 spec, `POST /api/alerts` description and examples | suspend (`minutes`), cancel, takeownership, releaseownership, assignownership (`userAccountID`) |
| Is the alert endpoint bulk? | 9.1 spec, request body `uuid-values`, example carries 2 UUIDs | yes, list of alert IDs; 200 returns an `alerts` array of per-alert records |
| Does an action validate endpoint exist? | 9.1 spec, all paths matching `valid` | only `/api/fleet-management/iam/saml-metadata/validate`, unrelated. **No action validation endpoint** |
| What is the full action surface? | 9.1 spec paths | `GET /api/actiondefinitions`, `POST /api/actions/{id}/query` (`populateAction`), `POST /api/actions/{id}` (`performAction`), `GET /api/actions/{taskId}/status` |
| Does the action catalog carry parameter metadata? | `GET /api/actiondefinitions` on DEVEL | 142 definitions, 43009 bytes, 38 to 130ms over 3 calls, byte-identical. Keys: `actionAdapterKindKey, canRecommend, contextAdapterKindKey, contextIds, contextResourceKindKey, displayName, id, scheduleEnabled, type`. **No parameter metadata**, confirming a catalog-only fingerprint cannot detect a defaults change |
| Alert state distribution | `GET /api/alerts?pageSize=1200` on DEVEL | 1124 alerts: `status` 1086 CANCELED / 38 ACTIVE; `controlState` 1124 OPEN / 0 other |
| What fields does an alert expose? | `GET /api/alerts` and `GET /api/alerts/{id}` on DEVEL | identical field sets: `alertDefinitionId, alertDefinitionName, alertId, alertImpact, alertLevel, cancelTimeUTC, controlState, links, resourceId, startTimeUTC, status, subType, suspendUntilTimeUTC, type`. **No `ownerId` or `ownerName` on any of 1124**, though the 9.1 schema declares both |
| Alert detail read cost | `GET /api/alerts/{id}` on DEVEL, 3 samples | 926 bytes, 28 to 31ms |
| Does `GET /api/reports/{id}` accept a report-definition ID? | DEVEL, definition `81f0f059-...` | **HTTP 404**, `"No such Report"` |
| Does a report definition carry a modification time? | `GET /api/reportdefinitions/{id}` on DEVEL | 200, 1661 bytes. Fields: `active, description, id, links, name, owner, subject, traversal-specs`. **No timestamp of any kind.** The list form drops `links` too. 74 definitions total |
| What does a report run return? | 9.1 spec, `POST /api/reports` | body `{resourceId, reportDefinitionId, traversalSpec, subject, publish}`; response is a `report` object with `status`, `completionTime`, `id`. **Not a task ID** |

Two things I deliberately did not measure, both because measuring them requires
a mutation:

- Whether `POST /api/actions/{id}/query` (populate) is side-effect-free and
  byte-stable across calls.
- Whether `ownerId` and `ownerName` become readable once an alert is owned,
  which decides whether the ownership verbs can be revalidated at all.

Both stay open risks in the record.
