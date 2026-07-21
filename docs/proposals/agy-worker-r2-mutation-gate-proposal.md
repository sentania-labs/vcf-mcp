# Antigravity Proposal: Round 2 Mutation Gate

## 1. Approach

I propose a **generalized mutation gate** with a single plan/apply path that covers all three families, keeping the total mutation tool count at exactly six. This honors record 001's mandate to minimize client context cost while extending plan-then-apply universally.

**Tool Surface (6 tools):**
* `list_action_definitions`, `populate_action`, `validate_action` (unchanged, action-specific).
* `plan_mutation(target_id, operation_class, operation_id, resource_id?, parameters?)` (replaces `plan_action`). The `operation_class` is an enum of `action`, `alert_ack`, or `report_run`.
* `apply_mutation(plan_id, hmac_token)` (replaces `apply_action`).
* `get_mutation_task(task_id)` (replaces `get_action_task`, generalizing async polling).

**The Plan Record and Fingerprints:**
The persisted plan record generalizes. It drops the action-specific fields at the top level and holds: `plan_id`, `key_identity`, `target_id`, `operation_class`, `operation_id`, `resource_id`, `payload_digest` (hash of the exact payload to be sent), `subject_fingerprint` (state of the target entity at plan time), `target_posture`, and `expiry`.

The `subject_fingerprint` is computed per family during `plan_mutation`:
* **action**: Hash of the `actiondefinition` record plus `contextResourceKindKey`.
* **alert_ack**: Hash of the alert's `status` and `cancelTime` from `GET /api/alerts/{operation_id}`.
* **report_run**: Hash of the report definition's modification timestamp from `GET /api/reports/{operation_id}`.

**Revalidation immediately before apply:**
At apply, before calling the mutation endpoint, the server re-fetches the target's state and compares it to the `subject_fingerprint` or performs a fresh validation.
* **action**: One extra API call. Re-run `POST .../validate` with the planned payload. If validation fails or yields new warnings not present at plan time, revalidation fails.
* **alert_ack**: One extra API call. `GET /api/alerts/{operation_id}`. If the alert is no longer `ACTIVE` (for example, already canceled or acknowledged), revalidation fails.
* **report_run**: One extra API call. `GET /api/reports/{operation_id}`. If the modification timestamp changed, revalidation fails.

**Failure States:**
* If the revalidation API call itself fails or times out: The apply is safely rejected with `revalidation_timeout`. The mutation was never sent.
* If revalidation fails due to state change (stale plan): The apply is rejected with a structured `stale_plan` error detailing what changed. It does not auto-generate a new plan, because doing so breaks the mental model that `apply` mutates. The operator must explicitly call `plan_mutation` again to see the new reality.
* If the actual mutation call times out after revalidation succeeds: Return `outcome_unknown` per record 001.

**Authorization and Scopes:**
Alerts and reports get their own grantable scopes (`alert_acknowledge`, `report_run`). The read-only default and prod hard-block apply identically; `apply_mutation` asserts the target's enablement flag before revalidation regardless of `operation_class`.

## 2. Risks

* **Action Validation Latency**: For `action`, doing a full validate immediately before apply doubles the heavyweight API work. Some actions might take seconds to validate, risking hitting the MCP server's HTTP timeout before the apply even fires.
* **Alert Volatility**: Alerts frequently flap or update their properties due to recurring symptom evaluation. If we hash too many properties, we will cause extremely high false-refusal rates for alert acks. Given one hour against DEVEL, I would ask one question: "If an active alert receives a duplicate symptom trigger, does its `updateTime` change?" If yes, the fingerprint must exclude `updateTime` and rely purely on `status == ACTIVE`.
* **Race Condition**: There is still a TOCTOU (time-of-check to time-of-use) gap between the revalidation API call and the actual mutation API call. We cannot eliminate it without a transactional API on the VCF Ops side (which does not exist), so we are only narrowing the window, not closing it.

## 3. Division-of-labor claim

I am best suited to own the generalization of the plan record and the `plan_mutation` / `apply_mutation` tool handlers. My proposal hinges on keeping the tool count exactly at six by using a discriminated input payload. JSON shaping to cleanly multiplex three distinct API families through one parameter schema is exactly my strength.

The revalidation logic per family (the extra API calls) should go to Claude, as it has the best grasp on mapping these to the specific VCF Ops API shapes from the recon phase.

## 4. Rough estimate

1.5 days to implement the generalized plan schema and the multiplexed `plan_mutation` and `apply_mutation` endpoints.

What would blow this up: If VCF Ops' `/api/actions/.../validate` endpoint is not idempotent or has side effects (some systems run dry-runs that actually create temporary state). If validate mutates, calling it at apply-time breaks the safety model, requiring us to design a completely different state-comparison approach.
