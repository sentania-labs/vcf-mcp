# Codex worker, round 2 mutation-gate critique

- Timestamp: 2026-07-21T17:30:35Z
- Branch: `codex/r2-mutation-gate`
- Protocol: phase 2 adversarial critique

## 1. Critique of claude-worker

**Strongest objection: returning a replacement plan from `apply_mutation`
crosses the operator-confirmation boundary.** The replacement has fresh state,
a fresh payload digest, and potentially a materially different summary. The
operator confirmed none of them. It is true that the replacement must still go
through a later apply gate, but that proves only that the server will not
mutate immediately. It does not prove that a tool-calling client will display
the replacement summary and obtain a new human confirmation rather than treat
the returned plan as the continuation of an already approved request. The safe
contract is that apply returns a denial and diff only, while an explicit
`plan_mutation` call creates the next confirmable artifact. I would change my
mind if the protocol made replacement plans unambiguously non-confirmable
until a distinct user-confirmation exchange, and this property were enforceable
server-side rather than dependent on client behavior. At that point the object
would not save the important operator round trip, so the claimed benefit would
also need to be restated.

1. **The proposed alert capability is built on an unverified verb.** The
   proposal says the 9.1 spec names `acknowledge`, `release`, `suspend`, and
   `assignownership`. The bundled 9.1 OpenAPI for `POST /api/alerts` instead
   describes `suspend`, `cancel`, `takeownership`, `releaseownership`, and
   `assignownership`; a search of that specification finds zero occurrences of
   `acknowledge`. This supports Claude's broader point that `alert_ack` is the
   wrong abstraction, but defeats the specific `alert:acknowledge` MVP and its
   grantability claim. “Acknowledge” may be a UI term for `cancel`, or 9.0.2 may
   differ, but neither should be guessed at a security boundary. I would change
   my mind on receipt of the exact DEVEL 9.0.2 OpenAPI operation or other
   read-only contract evidence mapping acknowledge to a supported verb.

2. **The action revalidation sequence names an upstream validation call that
   the OpenAPI does not expose.** The 9.1 contract has `POST
   /api/actions/{id}/query` (`populateAction`) and `POST /api/actions/{id}`
   (execution), but no action validation operation. `validate_action` in the
   six-tool design therefore cannot be assumed to mean a second server-side
   validation endpoint. Worse, populate is a POST, and the proposal correctly
   admits that its side-effect behavior is unproven, so the action revalidator
   is not yet a safe implementable contract. I would change my mind if the
   applicable 9.0.2 contract identifies a side-effect-free validation endpoint,
   or read-only evidence and vendor documentation establish repeated query as
   side-effect-free and define local validation precisely.

3. **The one-alert cap is an acceptable safety stop, but the proposal overstates
   what it establishes about partial success.** The OpenAPI proves a list input
   and a list-shaped 200 response, but documents only whole-request 200 and 500
   responses. That makes partial application a credible open risk, not an
   observed fact. The cap safely removes that risk from MVP and should remain,
   but the record should distinguish documented bulk support from unverified
   partial semantics. I would change my mind if a non-mutating vendor contract,
   synthetic upstream behavior derived from authoritative documentation, or a
   later approved mutation test demonstrates per-item partial application.

4. **`get_mutation_status` does not generalize cleanly for alerts merely because
   the adapter returns a local terminal state.** A 200 response contains alert
   objects, but without proven per-item success semantics it may only establish
   that a response arrived. Re-reading an alert can show current state, not
   causation by this request. Calling that a status projection risks upgrading
   inference to confirmation. I would change my mind if the exact alert response
   contract defines success per returned identifier, or the status schema
   explicitly labels readback-only results as inferred.

## 2. Critique of agy-worker

**Strongest objection: the report revalidation design addresses the wrong
resource through the wrong endpoint and hashes a field that does not exist.**
`report_run` consumes a report definition ID and creates a historical report.
The 9.1 contract reads definitions at `GET /api/reportdefinitions/{id}` and
historical runs at `GET /api/reports/{id}`. The `report-definition` schema has
no modification timestamp. Consequently, `GET /api/reports/{operation_id}`
cannot revalidate the definition, and this design can either reject every new
run because no historical report has that ID or inspect an unrelated report.
This is not a conservative failure mode. It means the proposed family adapter
cannot be implemented as written. I would change my mind if DEVEL 9.0.2
read-only evidence shows a different endpoint and a stable definition revision
field, with the precise field names recorded.

1. **The action path relies on a nonexistent validation endpoint.** The bundled
   OpenAPI exposes populate/query and execute, not `.../validate`. Saying the
   apply path makes “one extra API call” hides the unresolved choice between
   rerunning a POST whose side-effect safety is unknown and performing only
   local validation against possibly stale populated defaults. I would change
   my mind if the exact 9.0.2 OpenAPI identifies that endpoint or authoritative
   evidence proves the query call safe and the proposal is rewritten around
   it.

2. **The alert fingerprint rejects valid alert states and omits control state.**
   It requires `status == ACTIVE`, but the schema also defines `NEW` and
   `UPDATED`, both of which can still represent extant conditions. Meanwhile,
   `controlState` distinguishes `OPEN`, `ASSIGNED`, `SUSPENDED`, and
   `SUPPRESSED`, which is directly relevant to several supported alert verbs.
   Hashing only `status` and `cancelTime` cannot preserve ownership or suspension
   intent. I would change my mind if read-only 9.0.2 evidence establishes that
   the chosen verb is legal only for `ACTIVE` regardless of control state.

3. **The flat planner signature cannot express the capabilities it claims to
   multiplex.** One `operation_id`, one optional `resource_id`, and generic
   `parameters` do not model bulk alert IDs, multi-resource actions, or the
   structured report payload (`traversalSpec`, `subject`, and `publish`). This
   is not a discriminated union with bounded branches. It is an untyped payload
   with ambiguous identifiers, so malformed cross-family combinations can
   reach dispatch unless each adapter reconstructs a hidden schema. I would
   change my mind if each enum branch receives a closed, independently
   validated object schema and incomplete adapters fail registration.

4. **The plan record omits authorization and confirmation facts needed at the
   boundary.** It has no required capability scope, canonicalization/schema
   version, redacted operator summary, or digest binding the summary to the
   effective payload. `target_posture` and `payload_digest` alone do not show
   what the operator approved or which fine-grained capability apply must
   recheck. I would change my mind if those immutable fields are added and the
   confirmation token covers them.

5. **The generalized status tool assumes every mutation has a task ID.** Alert
   modification is documented as synchronous, while report creation returns a
   report object whose ID is polled at `/api/reports/{id}`. A single
   `get_mutation_task(task_id)` signature erases both handle type and target,
   inviting the actions status endpoint to be used for a report ID. I would
   change my mind if the handle is a typed server-issued reference bound to
   target, family, and upstream identifier, and local terminal operations do
   not pretend to have tasks.

## 3. Concessions

1. Claude was right that `alert_ack` names the wrong public operation unit. I
   treated acknowledgement as an established VCF Ops operation without first
   checking the endpoint. The contract exposes a general alert-modification
   endpoint with several verbs, and the exact mapping of “acknowledge” remains
   unproven.

2. Claude was right to separate `report:publish` from ordinary report
   generation. I included output options under one `mutate.report_run` scope and
   missed that `publish: true` makes a tenant-visible side effect with a wider
   blast radius.

3. Claude was right to put an explicit one-alert-per-plan cap on MVP. I named
   per-alert outcomes but did not make the implementation boundary decisive.
   Until partial semantics are known and modeled, single-alert plans are the
   safe shippable choice.

4. Antigravity was right that alert fingerprints must avoid volatile fields.
   My proposal left “fields that determine applicability” underspecified. A
   versioned projection must name exact safety fields and exclude presentation
   drift, although Antigravity's proposed field set is too narrow.

## 4. Changed position

I no longer support `alert_ack` as the discriminator. I support an `alert_op`
family with a closed verb-specific input union, with MVP registering only the
verb whose exact 9.0.2 contract and semantics are established. Scopes remain
verb-specific and capability-derived.

I now support one alert ID per MVP plan. Per-item outcomes remain the required
model before bulk is enabled, not a reason to expose unverified bulk behavior
now.

I would split `report:run` from `report:publish`, and I would not describe
action apply-time revalidation as populate plus validation until the safety of
populate and the existence of any upstream validation operation are settled.

I have not changed position on replacement plans. A stale apply must return a
denial and a redacted diff, not mint the next confirmable artifact inside the
apply response.

## 5. New recon performed

I performed no new live DEVEL recon. I read the vendor 9.1 OpenAPI at the
read-only knowledge-source path
`vcf-content-factory/reference/docs/operations-api-9.1.json`.

Actual contract measurements:

- `POST /api/alerts` accepts one `uuid-values` body containing N alert IDs and
  one string `action` query parameter. Its description names 5 verbs:
  `suspend`, `cancel`, `takeownership`, `releaseownership`, and
  `assignownership`. The specification contains 0 occurrences of
  `acknowledge`.
- The alert schema defines 4 status values (`NEW`, `ACTIVE`, `UPDATED`,
  `CANCELED`) and 4 control states (`OPEN`, `ASSIGNED`, `SUSPENDED`,
  `SUPPRESSED`).
- Report definitions are read at `GET /api/reportdefinitions/{id}`. Historical
  reports are read at `GET /api/reports/{id}`. The report-definition schema has
  9 properties and no modification timestamp.
- Report creation is `POST /api/reports` with `resourceId`,
  `reportDefinitionId`, `traversalSpec`, `subject`, and `publish` in the
  documented example.
- The action family exposes 4 paths in this specification: `GET
  /api/actiondefinitions`, `POST /api/actions/{id}`, `POST
  /api/actions/{id}/query`, and `GET /api/actions/{taskId}/status`. It exposes 0
  action validation paths.

These are specification facts, not observed 9.0.2 appliance behavior. Any
version difference remains an explicit open question for read-only DEVEL
recon.
