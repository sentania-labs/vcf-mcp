---
source-ref: 612bbe6ce7e33be9dabcb153be799c6b1b4ec193
source-commit: 612bbe6ce7e33be9dabcb153be799c6b1b4ec193
source-blob: a6f0f0cf86da7437fe97ada4e628801b7ae88798
source-path: docs/proposals/agy-worker-r3-p1-ballot.md
worker: agy-worker
round: round-3
phase: phase3
captured: 2026-07-26
---

# agy-worker Phase 1 Ballot

## Question 1: Does audit unavailability block process startup?
**Vote:** 1B
**Reasoning:** If the server refuses to boot because the audit volume is full, the Admin UI is taken down with it. The Admin UI is required for diagnostics, target posture changes, and reading the audit log itself. Taking down the Admin UI for a full audit volume turns a manageable disk issue into a total system outage. The audit failure must block tool execution, not process startup.
**Interest:** I proposed option 1B in my critique.

## Question 2: Audit storage format
**Vote:** 2A
**Reasoning:** A SQL table makes it trivial to delete records without leaving a hole, which undermines the append-only guarantee. NDJSON files are harder to selectively edit and are easily verifiable by line count. While WAL mode reduces reader-writer lock contention in SQLite, the backup API rotation procedure still introduces a crash window and operational risk. NDJSON with app-owned rotation is simpler, safer, and does not compete with the credential store's transactions.
**Interest:** I conceded to Claude's NDJSON in my critique.

## Question 3: Fixture generation and staleness
**Vote:** 3C
**Reasoning:** A manual recorder and generator pipeline practically guarantees fixture staleness. When the API drifts, the friction of manually re-running, re-scrubbing, and re-generating captures will encourage developers to test against old fixtures rather than keeping them updated. Nothing in Phase 1's scope solves this staleness problem, so we must explicitly accept it as an unsolved risk and budget nothing for it right now.
**Interest:** I raised the fixture staleness risk as an attack in my critique.

## Question 4: Is the retry bound actually bounded?
**Vote:** 4B
**Reasoning:** A generation counter alone prevents concurrent callers from all acquiring new tokens, but it does not prevent a single request from retrying infinitely if the new token also fails (e.g., if credentials are revoked mid-session). We need an explicit per-request retry counter to enforce "exactly once" semantics, as well as a target-configuration generation to handle configuration replacements.
**Interest:** I identified the unbounded retry loop attack in my critique.

## Question 5: What predicate does read-only enforcement actually key on?
**Vote:** 5B
**Reasoning:** My original GET-only proposal was factually unbuildable because VCF reads heavily use POST. However, relying purely on the capability registry (5A) leaves us vulnerable to the appliance silently ignoring unrecognized query parameters and returning unfiltered collections (as Claude measured). A frozen allowlist of (method, path template, permitted query parameter names) ensures the transport structurally refuses both unexpected methods and unbound queries.
**5-sub:** yes
**Interest:** I originally proposed a GET-only transport but conceded it was unbuildable in my critique.

## Question 6: Decomposition and slice ownership
**Vote:** 6B
**Reasoning:** Codex's contracts interface spine breaks the sequential dependency between the dispatcher, store, and client. Claude's correction to make the registration record an open versioned mapping prevents the registry from becoming a recurring serialization point. Moving skills out of delivery surfaces balances the otherwise oversized slice 3.
**6-sub:**
codex-worker owns the policy and persistence spine (contracts, store, migrations, keyring, target registry).
claude-worker owns the VCF read plane (client, domains, adapters).
agy-worker owns the delivery surfaces (Admin UI, MCP mount, deploy, CI) and the Skills surface as a separate piece.
**Interest:** I originally claimed the target registry and credential store in my proposal, but I am yielding it to codex-worker here because keeping the persistence spine unified under Codex's stronger schema is the better architectural cut. I am claiming delivery surfaces, CI, and skills, which aligns with my explicit documentation of the CI pattern.

## Objections
**Unsolved wrong-auth-source diagnosis:** As measured by Claude, a wrong auth source and a wrong password return byte-identical 401s. Even with the auth-source dropdown populated from unauthenticated endpoints, an operator who picks the wrong entry from the valid list will still get an unhelpful 401 error. We have no way to differentiate this at the API layer, meaning the operator experience for misconfigurations will remain poor.

## Scope check
**Gate 1 Credential Scope Blocker:** The delivered read-only service account is scoped to only 4 objects and zero VMs. If this is not fixed, Gate 1 will demonstrate an empty inventory, regardless of whether our implementation is perfectly correct. We must escalate to lab-admin immediately to widen the service account role scope to allow all objects on DEVEL before starting the build.

## Question 7: What does the dispatcher return when the TERMINAL audit write fails after the upstream call already succeeded?
**Vote:** 7C-with-payload
**Reasoning:** We must adopt the shape needed for Phase 2 right now to avoid rewriting the dispatcher choke point later. 7B makes sense for Phase 1 reads, but would be dangerous for Phase 2 mutations (the record 001 double-submit problem) if a client were to automatically retry. 7C correctly signals an ambiguous state that prohibits automated retry, forces the system out of readiness, and surfaces the call for reconciliation. I am voting `with-payload` because if the appliance successfully processed the request (read or mutation), dropping the returned data on the floor (7A) provides no security benefit while causing data loss; the client should receive the payload alongside the `outcome_unknown` state to aid in manual reconciliation.
**Escalate:** no. I agree with the provisional reading. The core of the audit invariant is that no unrecorded action can occur. The pre-execution attempt record ensures the intent, caller, and arguments are durably logged before the appliance is touched. The lack of a terminal record simply means the final outcome of the call is unknown, not that the action was unaudited. This is implementable in software and satisfies the constitution without requiring an escalation.
**Interest:** None.
