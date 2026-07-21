# Antigravity worker, round 2 mutation gate critique

- **Branch:** `agy/r2-mutation-gate`
- **Protocol:** phase 2 adversarial critique

## 1. Critique of claude-worker

**1. Returning a freshly issued plan inside apply_mutation's denial breaks the client contract and operator trust.**
This is my strongest objection. The gate's purpose is human confirmation. If `apply_mutation` fails revalidation and returns a new `Plan` object, the client has to be programmed to expect a `Plan` back from an `apply` call and prompt the user again. This mixes the planner and applier roles into one endpoint. More importantly, if the state changed enough to fail revalidation, the operator's original intent may no longer make sense. Forcing them to run a fresh `plan_mutation` tool call is the only way to ensure the LLM evaluates the new state before proposing a new plan to the human.
*What would change my mind:* A demonstration that standard MCP clients like Claude Desktop or Private AI Services natively support interactive re-prompting when a tool call designed to execute an action instead returns a new plan payload.

**2. Capping bulk alerts to one per plan destroys the UX for the most common alert workflow.**
Claude recognized the endpoint is bulk but punted by capping MVP to 1 alert. Operators acknowledge alerts in batches. Forcing 50 plan-apply round trips to clear an alert storm is an unacceptable degradation. Partial success must be modeled in the terminal states (for example `completed_with_failures`), as Codex suggested.
*What would change my mind:* Evidence from VCF Ops operators that they only ever acknowledge alerts one by one, making the cap practically acceptable.

**3. Relying on populate for revalidation is dangerous.**
Claude mandates re-running populate (`POST /api/actions/{id}/query`) at apply time. Since it is a POST, it has no idempotency guarantee, and my recon confirms it can generate dynamic defaults (like timestamps). Strict fingerprinting against this will cause spurious `stale` denials for perfectly valid plans.
*What would change my mind:* A curl trace proving that `POST /api/actions/{id}/query` returns byte-identical responses across time for all actions, guaranteeing no spurious digest drift.

## 2. Critique of codex-worker

**1. The action validate endpoint does not exist.**
This is my strongest factual objection. Codex requires apply to "call the VCF Ops validation operation where available." My recon against the 9.1 OpenAPI spec shows that there is absolutely no validation endpoint for actions. The only endpoint containing "validate" in the entire API is for SAML metadata. Therefore, Codex's preflight for actions falls back entirely to the `populate` POST call.
*What would change my mind:* A curl trace against DEVEL showing a hidden or undocumented `/api/actions/{id}/validate` endpoint that actually works.

**2. Spurious revalidation denials due to strict digest equality on populate.**
Like Claude, Codex relies on re-running populate and doing strict digest equality. Because populate returns a fresh execution template which can contain dynamic values, the digest will drift between plan and apply. A strict digest equality check on dynamic output will result in recurring false refusals.
*What would change my mind:* Proof that VCF Ops' action populate responses contain strictly static schemas and no dynamic defaults like generated IDs or timestamps.

**3. Ignoring the discriminated union rendering problem.**
Codex flags that Private AI Services might struggle to render the discriminated union schema, but proceeds with it anyway, offering an 8-tool hybrid fallback. If the union schema fails to render, the entire mutation surface is invisible to the client. This is a block-shipping risk that should be tested before amending the record.
*What would change my mind:* A successful test run showing that VCF Private AI Services and Claude Desktop correctly render and validate the proposed union schema.

## 3. Concessions

1. **I concede to Claude on the alert unit and name.** My proposal and Codex's both scoped `alert_ack`. Claude correctly pointed out that the endpoint is `POST /api/alerts?action=<verb>` and supports multiple verbs. Hardcoding "ack" names the wrong unit.
2. **I concede to Codex on bulk alert partial success.** Codex correctly identifies that the plan and audit model need per-alert outcomes. My proposal missed the bulk nature of the endpoint entirely, and Claude's cap to 1 is a non-solution.
3. **I concede to Claude on the get_mutation_status fallback.** Claude correctly notes that `POST /api/alerts` is synchronous and returns the terminal status immediately, so we don't need a polling mechanism for alerts.

## 4. Where I have changed my position

- **Alert Operation Naming:** I abandon `alert_ack` in favor of `alert_op` with a `verb` field, per Claude.
- **Bulk Alerts:** I change my position to support bulk alert operations. The plan schema must accept an array of IDs, and the audit model must handle partial success.
- **Action Revalidation:** I originally proposed re-running `validate` at apply. Since I have proven the endpoint does not exist, and re-running `populate` causes spurious digest drift, I now argue that **actions should not be revalidated via live API calls at apply time**. Revalidation for actions should only check the cached definition fingerprint. We must accept the TOCTOU risk for actions rather than breaking the gate with false refusals.

## 5. New recon performed

I ran `jq` queries against `vcf-content-factory/reference/docs/operations-api-9.1.json` to verify the API shape without mutating anything on DEVEL.

| Measurement | Finding |
| --- | --- |
| `POST /api/alerts` | Confirmed it takes an array of UUIDs and an `action` query param (e.g. `action=suspend`, `action=cancel`). Returns 200 OK with an array of the updated alert objects synchronously. |
| Action Validate Endpoint | Searched paths for `validate`. The only matching endpoint is `/api/fleet-management/iam/saml-metadata/validate`. There is no validate endpoint for actions. |
| Action Populate Endpoint | Confirmed it is `POST /api/actions/{id}/query`. The documentation states it returns populated values to be used as input for the action. |
