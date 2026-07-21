# Phase 3: ballots

Phase 2 is closed. All three critiques are committed. That round did what it
was supposed to do: it produced real attacks, three substantive concessions,
and one discovery that changes the assignment. I have independently verified
the two load-bearing facts, and both hold.

**Verified by me, against `vcf-content-factory/reference/docs/operations-api-9.1.json`:**

- The string `acknowledg` appears **zero times** in the entire 9.1 OpenAPI
  document.
- The action surface is exactly four paths: `GET /api/actiondefinitions`,
  `POST /api/actions/{id}`, `POST /api/actions/{id}/query`,
  `GET /api/actions/{taskId}/status`. The only path matching `valid` is
  `/api/fleet-management/iam/saml-metadata/validate`, which is unrelated.
  **There is no action validation endpoint.**

`docs/SPEC.md` 4.1 requires "alerts: alerts, symptoms, acknowledge". The API
has no acknowledge verb. That is a SPEC contract error, it is Scott's to
resolve rather than the team's, and I am escalating it. Do not vote on it and
do not propose a SPEC edit.

## Read before voting

| Artifact | Commit |
| --- | --- |
| claude-worker proposal | `ce6e6c05c166edf29bfc2f31a0041a370df0fc7e` |
| codex-worker proposal | `63567bf885c6a6fda1365ba3122c22c3fdcc8b45` |
| agy-worker proposal | `a08f6ae0ad64f4d3e2d1a05fab7fefc00e7d55e4` |
| claude-worker critique | `eb79162616299ec47b9f430c343beed828e7c906` |
| codex-worker critique | `9fbed793cdcf0377ee21086b91989d846bbaf32f` |
| agy-worker critique | `afa891fb9af2fc04f131aaa5368b08fbb081120a` |

All under `docs/proposals/`. Read all six with `git show` from your own
worktree. Read the two critiques of your own proposal especially carefully.

## What is already settled and is NOT on the ballot

These converged in phase 2. Do not re-argue them; if you think one is wrong,
say so under "objections" at the end rather than voting against it.

- **One generalized gate**, not dedicated plan/apply paths per family. All
  three converged.
- **A failed revalidation returns a denial with a diff and no usable token.**
  claude-worker withdrew the fresh-plan idea in full and in its own words. This
  was the round's sharpest split and it is now unanimous.
- **The operation unit for alerts is a verb**, not "ack". All three converged.
  The real verb set is suspend, cancel, takeownership, releaseownership,
  assignownership.
- **Scopes are per-verb and capability-derived**, per Scott's ruling 2. No
  alert verb is granted in MVP.
- **Plans are consumed on every apply attempt**, including failed
  revalidation. Terminal states are terminal.
- **`get_mutation_status` is a typed projection**, not an assumption that every
  family returns an actions task ID.

## The four questions

Vote on each. For each: pick one option, give your reasoning in your own words,
and **state your interest**. If you proposed the option you are voting for, or
if a peer's critique of you bears on it, say so plainly. A party voting its own
position is expected and allowed; concealing that it is doing so is not.

Voting against your own earlier position is a legitimate and useful outcome.

---

### Q1. Alert batch size in MVP

- **(a)** One alert ID per plan. A hard cap.
- **(b)** Bounded batch, with per-alert outcomes read back from the response's
  `alerts` array, and the bound written as a number in the record.
- **(c)** Unbounded bulk.

Context: claude-worker proposed (a), then withdrew it for (b) after finding
the 200 response is natively per-alert-keyed. codex-worker proposed per-alert
outcomes, then moved to (a) as the safe shippable MVP. agy-worker argued (a)
destroys the batch workflow. Note that how a *failed* member is represented is
undocumented and cannot be settled without mutating.

### Q2. Action revalidation at apply, now that no validation endpoint exists

This is the crux of the round. Defect 2 exists because a stale plan could
execute. The only candidate revalidation call for actions is
`POST /api/actions/{id}/query` (populate), which is a POST whose
side-effect-freedom nobody has proven and nobody may test without mutating.

- **(a)** Revalidate via populate, recording its unproven idempotency as an
  open risk in the record.
- **(b)** Do not make live calls for actions at apply. Compare the cached
  definition fingerprint only and accept the TOCTOU gap.
- **(c)** The record mandates pre-apply revalidation for every family. For the
  action family the source is populate, and whether populate is side-effect-free
  becomes a **blocking question for the Phase 2 gate**: action apply does not
  ship until it is answered.

agy-worker changed position to (b) in its critique. Weigh (b) carefully against
what this round was convened to fix: the external review's finding was that a
stale plan could execute a destructive action. Note also that actions are
already ungrantable until the Phase 2 gate under record 001 and Scott's
ruling 2, which may make (c) cheaper than it looks.

### Q3. Tool schema shape for `plan_mutation`

- **(a)** Nested discriminated union with a bounded schema per branch.
- **(b)** Flat optional scalars and string arrays (`action_id`, `resource_ids`,
  `alert_ids`, `verb`, `report_definition_id`, `parameters`), with the server
  rejecting any field not belonging to the named operation.
- **(c)** Typed per-family planners plus one generic `apply_mutation`.

Context: codex-worker proposed (a) and named the client-rendering risk itself.
claude-worker moved to (b) and argued (c) is backwards because it duplicates
the half of the gate carrying the security content. agy-worker wants the union
tested against a real client before committing. Nobody has tested any of these
against VCF Private AI Services. If your answer depends on a test nobody has
run, say what the record should do in the meantime.

### Q4. Does `report_run` ship in MVP?

`GET /api/reportdefinitions/{id}` on 9.0.2 returns `active, description, id,
links, name, owner, subject, traversal-specs`. No version, no timestamp, no
content hash. Definition content can change without any readable field
changing.

- **(a)** Ship, with a fingerprint bound to definition *identity*, and the
  record stating plainly that the check is shallow and what it cannot detect.
- **(b)** Defer `report_run`, per codex-worker's own stated rule that a family
  without a safe readback contract does not implement the operation.

Note `report:run` and `report:publish` are separate scopes, and `publish: true`
is tenant-visible. You may vote differently for the two if you argue it.

---

## Output format

Write `docs/proposals/<your-prefix>-worker-r2-mutation-gate-ballot.md` on your
existing branch:

    ## Q1
    **Vote:** (a|b|c)
    **Interest:** ...
    **Reasoning:** ...

...and so on for Q2, Q3, Q4. Then:

    ## Objections
    Anything in the settled list you think is wrong, or anything the four
    questions fail to ask. Write "none" if none.

Keep it tight. This is a ballot, not another critique. Reasoning that repeats
your critique verbatim is less useful than one paragraph saying what actually
decides it for you.

If your reasoning would change given a fact nobody has measured, name the fact.
I would rather record a contingent vote honestly than a confident one falsely.

## Constraints

Unchanged and binding. No production code. Read-only DEVEL recon only, nothing
against prod, no mutations anywhere ever. No new dependencies. No credentials.
No em-dashes anywhere including the commit message. `Co-authored-by:` trailer.
Do not push. Do not open a PR. Do not enter another resident's worktree.

Commit the ballot and report the full 40-character SHA. Use the real output of
`date -u` for timestamps.
