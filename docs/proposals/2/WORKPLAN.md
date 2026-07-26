# Phase 1 workplan

Companion to `docs/proposals/2/SPEC.md`. Authority is
`docs/decisions/009-phase1-build-synthesis.md`.

Nothing here has been built. This is the plan that starts when the principal
approves issue #2.

## Size, honestly

**15 to 21 dispatch-days of work across three doers, landing in roughly 6 to 8
elapsed dispatch rounds**, plus 1 to 2 rounds for Gate 1 verification and any
fleet-caddy correction. A dispatch-day is one worker's productive session, not a
calendar day.

Two of the three doers independently produced this band (claude-worker 15 to 21,
codex-worker 12 to 18 resident-days). agy-worker's 3 to 4 calendar days was
attacked by both peers as being the same scope priced at a fifth, and it does not
enter the plan.

The number most likely to be wrong is the delivery slice, which has the widest
variance, the least team experience, and a dependency on a lab handoff outside
the team's control.

## Sequencing

**Step 0, day-one spikes, before the slices start.** Both are cheap and both can
invalidate work if discovered late.

| Spike | Owner | Why it gates |
| --- | --- | --- |
| FastMCP identity injection from ASGI middleware into tool handlers | codex-worker | Every audit record and every authorization check in all three designs assumes it works. Nobody has verified it. It gates the dispatcher. |
| End-to-end Streamable HTTP smoke through fleet-caddy with the real client | agy-worker | Local SDK tests cannot reveal proxy buffering, auth forwarding, reconnect, or content rendering. The result can reorder the build. |

**Step 1, `contracts.py`.** codex-worker, one short commit, the only planned
serialization point. Defines `ToolContext`, `ToolSpec`, `Capability`,
`TargetRecord`, `TargetPosture`, repository protocols, and the **open versioned
registration mapping** with its small required core. The three slices proceed in
parallel from here.

**Step 2, the three slices in parallel.** Below.

**Step 3, integration on the round branch**, suite green, then one PR with one
external Codex review round.

**Step 4, Gate 1** with the principal, using the review packet in SPEC section
15.

## Slices

### Policy and persistence spine, codex-worker, 4 to 6 dispatch-days

`contracts.py`, the dispatcher package (sole ownership), capability and
outbound-contract enforcement, migrations, the encrypted target repository, the
versioned keyring and rotation state machine, API keys and scope intersection,
and the audit repository.

Acceptance criteria, which codex-worker's own scope check asked be pinned before
implementation starts:

- Dispatcher step ordering exactly as SPEC section 3, with each audit failure
  state (`attempt` write failure, terminal write failure) covered by a test.
- The registration mapping's **required core** is enumerated, and its extension
  rule is written down, so a per-family field is provably additive.
- `outcome_unknown` is a distinct terminal state in the response envelope,
  distinguishable by a client from both success and retryable failure, with the
  payload in a subordinate field.
- Free-space reservation accounting is specified numerically, not as "a
  conservative threshold".
- The test-only mutating capability runs through the real dispatcher against
  read-only, actions-enabled, and prod fixtures, asserting deny, allow, deny.
- `MUTATING == frozenset()` asserted in the production registry.
- An end-to-end test observes an audit record for every listed tool.

### VCF read plane, claude-worker, 4 to 6 dispatch-days

The target client, auth and target-configuration generations, TLS, the typed
error hierarchy, projection and result caps, all Phase 1 read adapters, the
synthetic fixture generator, and the contract tests.

Acceptance criteria:

- Exactly one token acquisition across N concurrent 401s, asserted.
- No re-auth on 403, asserted.
- Per-request retry counter bounds retry at exactly one under mid-session
  credential revocation, asserted.
- Target edit marks the old client closed, and its drain-or-cancel semantics are
  documented and tested.
- Every adapter declares its `(method, path template, permitted query parameter
  names)` triple and its projection version.
- Metrics caps refuse rather than truncate, with the cap named in the refusal.
- The fixture generator preserves reference equality, rejects unknown schema
  paths, and emits generator version, source API version, and generation date.
  A proof test asserts no raw capture token reaches output.
- Contract tests assert shape and monotonic properties, **never exact object
  counts**.

### Delivery surfaces, agy-worker, 8 to 12 dispatch-days

Application composition, MCP binding, the admin UI with record 004's full
hardening list, health and readiness, container packaging, the `ai-log-depot`
CI path, and the first deploy through the docker.int slot.

This is the largest slice and the one Gate 1 rests on most directly. It was
priced at 4 to 6 days in the original three-slice cut and re-priced here after
claude-worker's critique 1.7 attacked that number: record 004's hardening list
alone is nine requirements including recent-reauth, which carries its own state
and its own tests, and a first deploy through the slot model is high-variance
work nobody on this team has done.

**Do not defer CI and deploy behind admin and MCP.** That was the original
mitigation and it defers the long pole, which is how a tail becomes the
schedule.

Acceptance criteria:

- Every record 004 hardening requirement has a test.
- The auth-source picker is populated from the target's unauthenticated
  `GET /api/auth/sources`, plus a "Local users" entry.
- Security-relevant admin writes fail closed while audit is degraded (the
  decision 1 rider), asserted.
- `/healthz` reports audit writability, readiness, and the unreconciled
  `outcome_unknown` count derived from durable storage.
- Deploy verifies `/healthz` and rolls back to the prior digest on failed health
  without touching persistent volumes.

### Skills, agy-worker, 2 dispatch-days

Catalog load, digest verification, index regeneration check, four render paths,
and the three seed skills.

**Ownership conditions, from the critic's tiebreaking vote and binding on this
workplan:** skills is a **distinct workplan item with distinct review**, and is
**explicitly non-blocking relative to the Gate 1 deploy**. It does not ride the
delivery slice's estimate, finish line, or PR tail. If agy-worker's capacity
fails that test, this piece is redispatched to another owner rather than
silently folded into the delivery PR.

The suite-api auth walkthrough seed content is authored by claude-worker from
its measured recon and handed over as content. That is roughly one day of
content authoring and it does not make claude-worker a co-owner.

### Cross-cutting: the live tier, claude-worker, 1 to 2 dispatch-days

Budgeted separately because it appeared in no slice's file list and because it is
the answer to agy-worker's staleness dissent.

`pytest -m live`, host-allowlisted so the prod FQDN cannot be configured, with
an httpx event hook that raises on any method or path outside the enumerated
read set. **Required assertions include the section 4.2 parameter allowlist
against the real appliance**, since that is the one control no fixture can
validate. Run at every gate and after every appliance upgrade.

## Risk register

| Risk | Owner | Mitigation |
| --- | --- | --- |
| Delivery slice slips and Gate 1 slips on deploy rather than on the server | agy-worker | CI and deploy are not deferred behind admin and MCP; the fleet-caddy spike runs on day one |
| The registration contract becomes a recurring three-way edit | codex-worker | Open versioned mapping with a small required core; extension rule written down at step 1 |
| Metrics response shaping turns out to need more than a cap | claude-worker | Named as a constraint, not a solved design. If capping proves unusable in practice, response shaping for `stats/query` is a new slice that appears in nobody's estimate today |
| Fixture staleness | claude-worker | The live tier is budgeted, not optional; fixtures carry generator and API version metadata; freshness checked at the release gate |
| A new dependency turns out to be needed | any | Escalate. Do not add one. Use a JSON-compatible skills index rather than adding PyYAML |
| TLS answer is deferred indefinitely by never being asked | orchestrator | Carried as a named Gate 1 packet item and a TLDR question to the principal |
| Fingerprint pinning consumes a slice | not budgeted | Not built in Phase 1. A CA bundle is the preferred answer and it is the principal's call |

## What this round did not decide

- **Audit retention and archival.** No rotation ships in Phase 1. The retention
  policy is a decision owed to the principal, and it is cheaper to make with
  real data than to guess now.
- **Completed-report listing and download.** Deferred to Phase 2 in this spec,
  and flagged to the principal because it reduces SPEC 4.1's stated MVP surface.
- **The lab CA bundle.** Deployment trust material, therefore an escalation.
- **Whether VCF Private AI Services tolerates the tool surface.** Record 002
  flagged it as the largest external risk local design cannot settle. It becomes
  testable for the first time in Phase 1 and the smoke test is claude-worker's.

## Definition of done for the round

1. All four slices merged into the round branch with a pre-integration sign-off
   marker from a non-author resident naming the exact merged commit.
2. The integrated suite green on the round branch.
3. One PR to `main`, one external Codex review round, findings addressed in the
   same PR.
4. Record 009 signed by all three doers.
5. Gate 1 packet delivered and the two principal questions in it answered.
