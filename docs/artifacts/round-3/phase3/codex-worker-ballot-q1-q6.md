---
source-ref: e191214a9a86c5c674dfa9e7fe7bc7004377925a
source-commit: e191214a9a86c5c674dfa9e7fe7bc7004377925a
source-blob: 17bf1f7d1097ccb2ad58ae75723bbb848126c8f3
source-path: docs/proposals/codex-worker-r3-p1-ballot.md
worker: codex-worker
round: round-3
phase: phase3
captured: 2026-07-26
---

# Codex worker ballot: Round 3 Phase 1 build synthesis

- **Round:** 3, phase 3
- **Voter:** codex-worker
- **Branch:** `codex/p1-ballot`
- **Date:** 2026-07-24

## Question 1

**Vote: 1B.**

Audit failure must close MCP readiness and refuse every tool call, but it need
not remove the diagnostic surfaces that cannot invoke tools. Keeping health and
admin available makes the failure visible and recoverable without weakening the
tool-path invariant. Health must report degradation, readiness must remain
false, and admin operations available in this state must not create an
alternative unaudited execution path.

**Interest:** I proposed that health remain available for diagnosis.

## Question 2

**Vote: 2C.**

SQLite gives the dispatcher durable attempt commits, transactional state
transitions, and an audit view the admin UI can query using the same bounded
repository discipline as the other stores. Automatic selective deletion from a
live audit table is a poor match for append-only semantics, and archive rotation
adds correctness and recovery work that Phase 1 does not need. Phase 1 should
admit calls only while conservative free-space capacity remains and should
leave archival policy to a later approved design.

WAL mode is sufficient to keep ordinary audit writes and admin reads from
blocking each other at the expected Phase 1 concurrency. It does not by itself
make backup, integrity verification, and row removal safe or simple, so it does
not rescue 2B's automatic rotation plan. The build must still test busy
timeouts, concurrent writers, disk exhaustion, and crash recovery.

**Interest:** I proposed 2B and named 2C as my reduced-scope fallback. I now
prefer 2C.

## Question 3

**Vote: 3B.**

Raw material outside the worktree removes an easy staging failure. Path-level
allowlisting closes leakage channels in keys and embedded URLs, deterministic
pseudonyms preserve the reference relationships the contracts exercise, and a
raw-token proof test provides a concrete rejection criterion. Those controls
are all necessary because value-only substitution can both leak identity and
destroy fixture meaning.

Nothing intrinsic to 3B solves staleness. Phase 1 should address it
operationally by recording the fixture generator version, source API version,
and generation date in fixture metadata, then making a read-only live contract
refresh and review a release-gate task. CI remains hermetic and does not capture
live data.

**Interest:** I proposed all four corrections that distinguish 3B.

## Question 4

**Vote: 4B.**

The authentication generation limits acquisitions within a live client, not
the lifetime of an individual request. An explicit request-local retry count
makes the one-retry rule invariant under every interleaving and makes the
second 401 a typed terminal error. A distinct target-configuration generation
is also required so an in-flight request cannot return a result obtained under
credentials or TLS policy that an administrator has replaced. Target edits
must mark the old client closed, reject retries on it, and either drain or
cancel its in-flight work under documented semantics.

**Interest:** I asserted exactly one retry in my proposal but did not make the
request-local counter explicit. I identified the separate target-generation
problem in my critique.

## Question 5

**Vote: 5B.**

Semantic capability is the authorization predicate. The frozen method, path
template, and permitted-query-name allowlist is an independent outbound
contract that prevents an adapter typo from broadening a query or reaching an
undeclared endpoint. The measured behavior for an unknown query name makes
that protection material: a misspelling can return a 200 response containing
the full 517-object collection. A fixture will normally validate its own
expected URL and cannot establish how the appliance treats an unknown
parameter.

5C is not a meaningful independent policy. Its authentication exceptions
already turn it into a method-and-path allowlist, and GET does not prove
non-mutation. 5A correctly models authority but lacks the outbound contract
needed to contain endpoint and parameter mistakes.

**5-sub: yes.** Register a test-only mutating capability through the real
registration and dispatcher path, and assert denial for read-only and prod
fixtures plus the intended policy result for an actions-enabled devel fixture.
Keep the empty production mutation-set tripwire too. One proves the Phase 1
catalog contains no mutation, while the other proves the dormant denial branch
works.

**Interest:** I proposed 5C, then conceded in my critique that the measured
POST reads invalidated that design. I proposed the test-only mutation.

## Question 6

**Vote: 6B.**

The interface spine gives one resident ownership of the dispatcher and policy
seam while letting repositories and adapters implement against narrow
protocols. The registration record must be an open, versioned mapping with a
small required core, otherwise family-specific controls turn the shared
contract into a recurring merge point. Moving skills out of delivery also
keeps the Gate 1 critical surface from absorbing a distinct catalog, rendering,
and exposure problem.

6C leaves final dispatcher assembly as integration work, which is both the
hottest correctness seam and work the orchestrator may not perform. 6A has the
right ownership shape but an unnecessarily fixed contract and an oversized
delivery slice.

**6-sub:**

- **codex-worker:** policy and persistence spine, including `contracts.py`,
  dispatcher ownership, capability and outbound-contract enforcement, target
  registry, credential envelope and rotation state machine, API keys, and audit
  repository.
- **claude-worker:** VCF read plane, including the target client, authentication
  and target generations, projections and result caps, all Phase 1 read
  adapters, synthetic fixture generator, and contract tests.
- **agy-worker:** delivery surfaces, including application composition, MCP
  binding, admin UI, health and readiness, container packaging, and the
  `ai-log-depot` CI and deployment path.
- **agy-worker:** skills as a separately planned and separately reviewable small
  piece, not as an implicit subdirectory of the delivery slice. If capacity
  requires another owner, the orchestrator should dispatch this piece
  explicitly rather than allowing shared ownership.

This preserves my Phase 1 claim to the policy and persistence spine. It rejects
agy-worker's conflicting claim to the target registry and credential store.
Assigning agy-worker the concrete delivery, CI, and separate skills work does
not create a new claim for me.

## Objections

The settled items are sound. One audit point still needs exact wording in the
synthesis: free-space admission and a durable attempt record can prevent a
tool from starting without audit capacity, but software cannot guarantee a
terminal write after an upstream call if the storage device fails physically.
Such a call must return a typed `outcome_unknown`, must never invite automatic
retry, and must force readiness false. If the constitution is interpreted to
require a durable terminal record even through physical media failure, that
requirement is not implementable and must be escalated to Scott rather than
papered over.

Fingerprint pinning also remains underspecified. Normal certificate validation
cannot complete a handshake against an untrusted self-signed chain and then
perform a post-handshake fingerprint check. Phase 1 should prefer a mounted CA
bundle. If direct fingerprint pinning remains required, the workplan must
budget a transport implementation that verifies every connection and an
explicit, unauthenticated first-trust ceremony.

## Scope check

The six decisions are sufficient to start the consensus spec, but the workplan
must define acceptance criteria for the seams they create before Scott
approves implementation: dispatcher ordering and audit failure states, the
required core and extension rules of the versioned registration mapping,
target-edit drain or cancellation semantics, free-space reservation accounting,
and the fixture freshness release gate. It must also state the exact Phase 1
tool inventory and per-tool method, path, query-name, projection, pagination,
and result-cap contracts. Those are specification tasks for this round, not
implementation code.
