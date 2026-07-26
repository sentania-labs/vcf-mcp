# Round 3, phase 3: ballots on the Phase 1 build synthesis

Phases 1 and 2 are closed. Three proposals and three critiques are committed.
The critique round did its job: it produced real attacks, several substantive
concessions, and two measured reversals. This is the ballot phase. You are
voting, not proposing a new design.

## Verified by the orchestrator before this dispatch

**The Gate 1 blocker is resolved and I re-measured it myself, live, today
(2026-07-24), against DEVEL with the delivered read-only service account:**

```
GET /suite-api/api/resources?pageSize=1  ->  pageInfo.totalCount: 517
GET /suite-api/api/adapterkinds          ->  21 adapter kinds
GET /suite-api/api/resources?adapterKind=VMWARE   -> totalCount: 169
GET /suite-api/api/resources?adapterKind=CONTAINER -> totalCount: 52
```

The account previously saw 4 objects. It now sees 517. Scott widened the role
scope himself. **Do not re-verify this by hitting the appliance again unless a
question below actually turns on it**; it is measured and recorded. Its
consequence for your ballot: the "Gate 1 demonstrates an empty inventory"
concern is closed, and payload-size and projection arguments that were softened
by the 4-object world are back at full force. claude-worker's measured
`stats/query` figure of 137,808 bytes for ONE resource at `maxSamples=1` now
sits on top of a 517-object inventory.

Recon rules are unchanged: DEVEL only, read-only, never PROD, never a mutation.

## Read before voting

| Artifact | Commit |
| --- | --- |
| claude-worker proposal | `bfc23827ee5fa47e169a7c0059414c2688d25060` |
| codex-worker proposal | `ae239552ae857294c01adcb4901fc943614ebb20` |
| agy-worker proposal | `f136b2aa3a13f3f0637e4d5215b37e18df35fbe8` |
| claude-worker critique | `48b68d0746779955358953103e6838c56f5ae174` |
| codex-worker critique | `63b3f4b1d818147caa555f87fe3d61d88ae870fd` |
| agy-worker critique | `4fd8004bb909eb841a1d4e57bcae5bb0c884e366` |

All are reachable from your worktree via `git show <sha>`. Files live under
`docs/proposals/` except agy's proposal, which is `phase1-proposal.md` at the
repo root of its commit. Read all six. Read the critiques of your own proposal
especially carefully.

## Already settled in phase 2, NOT on the ballot

These converged. Do not re-argue them. If you think one is wrong, say so under
"objections" at the end rather than voting against it.

- **Send `Authorization: OpsToken`.** All three measured both `OpsToken` and
  `vRealizeOpsToken` returning 200; the appliance keeps a case-insensitive
  allowlist of scheme names. Record 006 selects `OpsToken`. agy-worker's
  consistency-with-the-reference-client argument is noted and does not survive.
  The alias gets a code comment, not a behavior change.
- **Re-auth fires on 401 only, never 403.** claude-worker measured
  `POST /api/events/query` returning 403 with an HTML body for our ReadOnly
  account. A client that re-auths on "auth-ish non-2xx" burns an acquire on
  every events call forever.
- **Error decoding must not assume JSON.** Bad token yields JSON, bad scheme
  yields HTML.
- **An authentication generation counter, captured before the request and
  rechecked under the lock, is the right single-flight algorithm.** All three
  converged; agy-worker and codex-worker both conceded to claude-worker's
  formulation. Question 4 below is only about the *retry bound*, not about this.
- **Never parse `releaseName` to select behavior.** `9.0.2.0` reports
  `major/minor` as `2/2`.
- **`presence of a NEXT link does not mean more pages`.** Compare
  `(page+1)*pageSize` against `totalCount`.
- **HMAC-keyed argument digests with purpose-separated keys**, beating bare
  SHA-256, because Phase 1 arguments are low-entropy and enumerable offline.
  claude-worker conceded this in writing.
- **Length-prefixed AAD encoding** over a delimiter join. claude-worker
  conceded this in writing.
- **Never commit a captured byte from a live response.** The disagreement in
  question 3 is about *how* synthesis is done, not whether raw capture may be
  committed. It may not.
- **`httpx.MockTransport` for the fixture tier**, over a local ASGI mock
  appliance. claude-worker conceded to agy-worker on this.
- **Per-target TLS configuration on that target's own `httpx.AsyncClient`**,
  never a process-global disable.
- **Report *run* is a mutation per record 007 and ships in no form in Phase 1.**
  The SPEC's older `list/run/download` line does not override the later record.

## How to vote

For each of the six questions: **pick exactly one option**, give your reasoning
in your own words, and **state your interest** ("I proposed option B", "I
conceded this in my critique", "no interest"). A party to a dispute still votes;
declaring the interest is what keeps that honest.

If you think a question is malformed or its options miss the real answer, you
may vote `OTHER` and specify, but you must say precisely why none of the listed
options is adoptable. Do not use `OTHER` to smuggle in a fourth option you
merely prefer.

Write your ballot to `docs/proposals/<you>-r3-p1-ballot.md` and commit it to
your branch with a `Co-authored-by:` trailer naming you. Commit before your cap
expires; an uncommitted ballot is not a ballot.

---

## Question 1: does audit unavailability block process startup?

Not "does a failed audit write fail the tool call", and all three of you agree the
**attempt** record is written before the handler runs and that its failure
refuses the call. This question is only about the process.

- **1A.** Unwritable audit volume at startup refuses to boot. Exit non-zero.
  (claude-worker's proposal, section 1.7.)
- **1B.** The process starts. `/healthz` and the admin UI stay up and report the
  degraded state; MCP readiness is false and every tool call fails closed.
  (agy-worker's critique attack 1; codex-worker's proposal says health stays
  available so the operator can diagnose.)

agy-worker's argument, verbatim: "If the server refuses to boot or Uvicorn
crashes because the audit volume is full, the Admin UI is taken down with it.
The Admin UI is required for diagnostics, target posture changes, and reading
the audit log itself." claude-worker's counter is that an outage saying "the
audit volume is full" is a good outage and that softening an unconditional
constitutional invariant is an escalation, not a code comment. Note that 1B does
not soften the invariant on any *tool path*, it only keeps a surface that runs
no tools alive.

## Question 2: audit storage format

- **2A.** NDJSON append-only files on the audit volume, app-owned rotation
  (daily filename plus size cap plus retained-file count). (claude-worker 1.7.)
- **2B.** A separate SQLite database on the audit volume, monthly archive
  rotation via the SQLite backup API with an integrity check before row removal.
  (codex-worker.)
- **2C.** 2B's storage with codex-worker's own stated fallback promoted to the
  primary plan: SQLite, **no automatic rotation at all** in Phase 1, plus an
  early free-space admission refusal. (claude-worker's critique 1.5 recommends
  exactly this; codex-worker's proposal lists it as the reduced scope.)

Weigh: claude-worker argues a SQL table is the one format where selective
deletion leaves no hole, and that NDJSON is verifiable by size and line count.
codex-worker argues one transactional model, atomic revocation, and an admin UI
that can query the log without someone writing a reader. agy-worker attacked the
SQLite backup path for locking contention on the hot path of every tool call;
note that WAL mode is the standard answer to that and say whether you think it
is a sufficient one. Nobody has benchmarked this.

## Question 3: fixture generation and staleness

- **3A.** Recorder writes raw capture to a gitignored directory inside the
  worktree; a generator emits structurally-similar synthetic fixtures carrying
  no original byte; a CI scanner backstops. (claude-worker section 5.)
- **3B.** 3A, plus codex-worker's four corrections: raw captures live **outside
  the worktree entirely** (a gitignored path is defeated by `git add -f`); an
  explicit allowlist of response **schema paths**, not just values, because
  object keys and URL path segments can carry lab identity; **deterministic
  pseudonyms that preserve reference equality**, because independently replacing
  every string destroys the identity relationships pagination and link parsers
  are supposed to be tested against; and a proof test that no raw capture token
  appears in generated output.
- **3C.** Either of the above, but the round explicitly accepts fixture
  staleness as an unsolved problem and budgets nothing for it.

agy-worker's staleness attack, verbatim: "this approach practically guarantees
fixture staleness. When the API drifts, the friction of manually re-running and
re-scrubbing captures will encourage developers to test against old fixtures
rather than keeping them updated." Voting 3B does not answer that. If you vote
3B, say in one sentence what actually addresses staleness, or say plainly that
nothing in Phase 1 does.

## Question 4: is the retry bound actually bounded?

agy-worker found a possible unbounded retry: a caller that 401s, waits, sees the
generation moved, retries with the winner's token, and 401s again because the
credential was revoked mid-session. The generation counter bounds *acquisitions*
per storm. It does not obviously bound *retries per request*.

- **4A.** The generation counter alone is sufficient; a caller that finds the
  generation moved retries once and a second 401 is a typed error. No extra
  state. (Both claude-worker and codex-worker assert "retry exactly once" but
  neither carries an explicit per-request counter.)
- **4B.** Carry an explicit per-request retry counter in addition to the
  generation counter, so "exactly once" is a property of the request object
  rather than of the interleaving. Plus codex-worker's separate finding: a
  **target-configuration generation**, checked before retry and before returning
  a result, with old clients marked closed and defined drain semantics on a
  target edit, because the auth generation is single-flight only within one live
  client object and an admin edit replaces the object underneath in-flight
  requests.

## Question 5: what predicate does read-only enforcement actually key on?

This is the round's fork 4 and it moved twice. claude-worker's proposal said
verb-based gating was "unbuildable" because reads are POST; claude-worker's own
critique then measured that every Phase 1 read family has a working GET form and
**withdrew that claim in writing**. So GET-only is buildable. The question is
whether it is right.

- **5A.** Capability registry only. Tools declare a semantic capability;
  `MUTATING` is an empty frozenset in Phase 1; the dispatcher checks capability
  against target posture. The transport does not gate on verb.
- **5B.** Capability registry **plus** a frozen per-tool allowlist of
  `(method, path template, permitted query parameter names)` declared at
  registration, which the transport refuses to issue outside of.
- **5C.** GET-only base transport with named token-path carve-outs, as
  codex-worker proposed.

Two measured facts bear on this and you should engage both. First,
claude-worker's critique 1.2: codex-worker's rule is already "GET **plus the
narrowly named token acquire and release paths**", and those carve-outs are
POSTs that create and destroy session state, so the enforced predicate is
already `(method, path)` in an allowlist and the verb is carrying no independent
weight. A Phase 2 mutation shaped as a GET passes a verb test.

Second, claude-worker measured that **this appliance silently ignores
unrecognized query parameters and returns the unfiltered collection**:
`?identifier=<uuid>` (a plausible misspelling of `?resourceId=`) returns
totalCount 4 rather than 1, with a 200 and no error. Against the now-517-object
inventory this is materially worse than when it was measured. Fixture-backed
tests cannot catch it, because the mock answers the URL it is given.

Also vote on the sub-question, as `5-sub: yes` or `5-sub: no`:
**should Phase 1 register a test-only mutating capability and run it through the
real dispatcher against read-only, actions-enabled, and prod fixtures?**
codex-worker's attack 6 says asserting `MUTATING == frozenset()` proves Phase 1
declares no mutation but does not prove a mutation would be *denied*, and that
otherwise Phase 2's first mutation both activates and tests the choke point.
claude-worker's counter-consideration is that its empty-set assertion is a
deliberately annoying tripwire that makes adding a mutating capability a
visible, greppable act in a diff. These are not mutually exclusive.

## Question 6: decomposition and slice ownership

- **6A.** codex-worker's `contracts.py` interface spine, three horizontal
  slices: policy/persistence spine, VCF read plane, delivery surfaces.
- **6B.** 6A with claude-worker's critique 1.6 correction: the registration
  record is an **open versioned mapping with a small required core**, not a
  fixed signature, so a per-family field (the metrics sample cap is the concrete
  example) is an additive adapter change plus a dispatcher reader, rather than a
  three-way edit on the hottest file. Plus critique 1.7's rebalance: **skills
  moves out of delivery surfaces** into its own small piece, because delivery is
  oversized and is the slice Gate 1 depends on most directly.
- **6C.** claude-worker's original four-layer cut with `dispatch.py` assembled
  last against interfaces.

Note that codex-worker's attack 7 rejects claude-worker's shared ownership of
the dispatcher outright: "One resident must own the dispatcher package and
publish narrow protocols first," because "assemble last" shifts integration work
to the orchestrator, which is forbidden to write code. claude-worker's critique
section 4 independently arrives at the same three-way split codex proposes.

Also vote on the sub-question, as `6-sub:` followed by your assignment:
**who owns which slice.** The standing claims are: codex-worker claims the
policy/persistence spine (and record 003 already assigned it the envelope and
rotation state machine); claude-worker claims the VCF read plane on the strength
of having measured the appliance's actual behavior, and explicitly declines the
store; agy-worker claims the target registry and credential store, which
**collides with codex-worker's claim**. claude-worker's critique 2.11 notes that
agy-worker is the only one of the three who wrote the `ai-log-depot` CI path
concretely, and that admin UI, skills, and CI are otherwise claimed by nobody.
Vote the assignment you think is right, including for yourself, and say whether
you are claiming something you did not claim in phase 1.

---

## After the six questions

Add two closing sections.

**Objections.** Anything you think is wrong that was not on the ballot,
including anything in the "already settled" list. State it plainly. A losing
objection gets recorded verbatim in the decision record, so write it as you want
it read.

**Scope check.** This round's deliverable is a **consensus spec and workplan**
that goes to Scott for approval on a GitHub issue. **No implementation code is
written this round.** If you believe the six questions above leave a hole that
would block starting the build the moment Scott approves, name it in one
paragraph. This is the last cheap moment to notice.
