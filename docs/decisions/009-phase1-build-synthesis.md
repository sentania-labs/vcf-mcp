# 009: Phase 1 build synthesis

- **Status:** accepted. Approved by the principal on GitHub issue #2,
  2026-07-24T21:41:47Z. See "Amendment 1".
- **Round:** 3, the Phase 1 read-only build
- **Lane:** full protocol (blind proposal, adversarial critique, ballots,
  synthesis)
- **Workers dispatched:** claude-worker, codex-worker, agy-worker
- **Protected path in scope:** `src/vcf_ops_mcp/`
- **Decided:** 2026-07-24
- **Supersedes nothing. Depends on** records 001, 002, 003, 004, 005, 006, 007,
  008.

## Amendment 1: the principal approved this record unconditionally

**Authority:** principal approval on `sentania-labs/vcf-ops-mcp#2`,
2026-07-24T21:41:47Z. The comment is the single word `approved`, which is the
GitHub-issue pipeline's exact authorization token. The approved content is
pinned at commit `5940ea8c8458aac24ff8d8a18bd753c6345ae473` under
`docs/proposals/2/`, and this amendment changes nothing about what was
approved. Implementation is authorized from this point.

Three questions were carried to the principal in `docs/proposals/2/TLDR.md`
rather than being decided by the team. He approved without answering any of
them individually. **An unconditional approval of a spec that states its own
answer to a question is an approval of that stated answer**, so each resolves
as the spec already had it, and each stays open as a Gate 1 packet item where
the spec said it would:

1. **Reports family scope.** Phase 1 ships **report definitions listing only**.
   Completed-report listing and download move to Phase 2 with the run path.
   This is the reduction against `docs/SPEC.md` 4.1 that the TLDR flagged, and
   it is now authorized. The read plane's estimate is unchanged, since the
   approved estimate already assumed this scope.
2. **TLS trust material.** The first DEVEL registration ships with per-target
   verification disabled, honestly labelled as such in the admin UI. A mounted
   lab CA bundle remains the preferred answer and remains the principal's call.
   It is carried in the Gate 1 packet so that "verification off" cannot become
   permanent by never being raised again. Fingerprint pinning is not budgeted
   and is not built.
3. **The audit invariant reading.** The team's reading stands as written in
   decision 7-sub: a durable pre-execution attempt record, plus a typed
   `outcome_unknown` terminal state, plus reconciliation, plus fail-closed,
   satisfies "no tool path ships without its audit write". Both conditions the
   ballots attached are met, the reading is written down here, and it is a named
   Gate 1 packet item. It remains the principal's invariant and he may overrule
   the reading at Gate 1.

No other term of the spec or workplan is changed by this amendment.

## Amendment 2: what the sign-off round found, and four rulings

The sign-off dispatch asked each doer to confirm or deny six specific claims
rather than to "sign off". It found real defects in this record, which is the
second round running that the specific-confirmation framing has done so.
**codex-worker withheld its signature**, correctly. Everything below is a
correction to this record's presentation, to the Gate 1 packet, or to step 1's
scope. **No decision is changed.**

### Confirmed defects in this record, now fixed above

1. **codex-worker's fingerprint-pinning objection was paraphrased, not quoted.**
   It sat in "Open objections not resolved by a ballot", where every neighbouring
   entry is verbatim, as orchestrator prose. The orchestrator verified this
   against the ballot rather than taking it on report: confirmed, and fixed. The
   objection is now reproduced verbatim. `docs/decisions/README.md` says verbatim
   means the objector's own words, and a section that quotes two objectors and
   paraphrases the third is exactly the failure that rule exists to prevent.
2. **claude-worker's reports objection was front-truncated without a mark**,
   dropping "Not on the ballot and it should have been.", which was its only
   procedural objection of the round and appeared nowhere else in this record.
   Restored.
3. **Two tail truncations were unmarked** (claude-worker's reports remedy, and
   the operative ask in its TLS objection). Both restored in full.

codex-worker also notes that its audit-finalization objection is accurately
represented in decisions 7 and 7-sub but synthesized rather than quoted. It did
not condition its signature on that and the orchestrator has not rewritten those
decisions, which argue the position rather than merely record it.

**agy-worker's quoted objection was checked against its ballot independently and
is verbatim**, so its confirmation on that point holds.

### Ruling 1: numeric thresholds are the slice owner's to derive and declare

codex-worker withheld partly because the free-space reservation is not pinned
numerically anywhere, while the acceptance criterion demands it be "specified
numerically, not as 'a conservative threshold'". It asks that this record or the
workplan supply the number before implementation.

**Ruled: the criterion requires that the number be stated, derived, and tested,
not that the orchestrator invent it.** The slice owner derives it, states the
derivation where the number lives, tests it, and puts it in the Gate 1 packet as
a number somebody can argue with. This is not an evasion of the criterion, it is
the criterion: the defect the criterion names is an unfalsifiable adjective, and
a declared number with a stated derivation is falsifiable.

This is ruled rather than balloted because it is not a fork between competing
designs, and because **claude-worker independently proposed exactly this pattern
for the symmetric gap in its own slice** (the metrics cap, which SPEC section 5
defines as a bound on a product with no numeric value anywhere), saying it would
derive it from the measured 137,808 bytes, state the derivation in the adapter,
and record it "so that 'claude picked a number' is a declared act rather than an
inherited constant". That is the right pattern and it applies symmetrically. The
orchestrator does not write code and will not be the party supplying constants
to a slice it cannot test.

Two consequences bind:

- **codex-worker additionally owes the accounting semantics**, which are a real
  gap and not merely a number: what the reservation covers (terminal row, WAL
  growth, checkpoint headroom), and how concurrently admitted calls consume and
  release it. It owns the dispatcher and the audit repository, so this is inside
  its slice, and it is added to that slice's acceptance criteria.
- **claude-worker's metrics cap** carries the same obligation in the same form.

### Ruling 2: `contracts.py` carries a target-change invalidation protocol

claude-worker found a cross-slice seam that step 1 does not cover. The criterion
"target edit marks the old client closed, and its drain-or-cancel semantics are
documented and tested" spans three slices: the client registry is claude-worker's,
the target repository is codex-worker's, and the admin write that performs the
edit is agy-worker's. Step 1's enumerated contents include no target-change
notification or client-invalidation protocol.

**Ruled: adopted.** `contracts.py` carries a target-configuration-generation and
invalidation protocol at step 1. Decision 6's open-mapping correction exists
precisely to stop a shared contract becoming a recurring three-way edit, and a
mechanism three slices must agree on that is absent from the only planned
serialization point is that failure in advance. This is added to step 1's scope
and is the reason step 1 is worth its serialization cost.

### Ruling 3: reports scope becomes a Gate 1 packet item

Amendment 1 said each of the three principal questions "stays open as a Gate 1
packet item where the spec said it would". claude-worker checked that clause
instead of accepting it and found it false for one of the three: reports scope is
**not** in SPEC section 15's packet list, only the audit reading and TLS are. So
the one question with no scheduled re-ask was the one whose discovery point would
otherwise be after the family is built.

**Ruled: reports scope is added as a Gate 1 packet item.** The exposure was
already bounded (SPEC section 6 prices the reversal at roughly one dispatch-day),
but bounded is not the same as scheduled.

### Ruling 4: the audit-reading question is surfaced ahead of Gate 1, not in it

claude-worker signed the audit-invariant reading as honest while naming it the
thinnest of the three inferences, because the TLDR asked the principal for an
affirmative word and got a bare `approved`. Its point stands on cost rather than
on honesty: decision 7's own reasoning is that a terminal state on the
dispatcher's public contract is expensive to change late, touching the
dispatcher, every tool's response contract, the admin UI, the reconciliation
surface, and any client. An overrule at Gate 1 lands at the moment this record
itself calls the worst time.

**Ruled: adopted.** The orchestrator surfaces the audit-invariant reading to the
principal ahead of Gate 1 rather than only inside the packet, flagged as cheaper
answered early. It stays a packet item as well.

### A process note on the sign-off round itself

The three signatures were not of comparable depth. claude-worker's ran 256 lines
and produced four of the five findings above; codex-worker's ran 69 and produced
the withholding; agy-worker's ran 8 lines in a 96-second dispatch and confirmed
all six items, including that the acceptance criteria for the largest slice in
the plan (delivery, 8 to 12 dispatch-days) are "unambiguous, directly testable,
and buildable as written", with no specifics offered. Its one checkable claim,
that its own objection is quoted verbatim, was independently verified and is
true. Nothing is being taken away from it. It is recorded because this is the
second consecutive round in which this seat has produced the least scrutiny on
the largest slice, and because the next orchestrator run should weigh a
confirmation from it accordingly rather than reading three signatures as three
equal checks.

## Sign-off status

Sign-offs were collected at implementation dispatch, per
`docs/decisions/README.md`. claude-worker and agy-worker signed at commit
`1d44971`, before Amendment 2 existed. codex-worker withheld and signed after
the corrections. **Amendment 2 changes no decision**: it repairs quotations,
schedules two questions, and adds scope to step 1 at a doer's own request, so
the earlier signatures are not stale on any decided term. See "Sign-offs" at the
end of this record.

## Cited artifacts

Every claim in this record traces to one of these. All six are reachable from
the tag `artifacts/r3-p1-proposals-critiques`; the ballots and the critic vote
are reachable from this round branch.

| Doer | Proposal | Critique | Ballot | Q7 ballot |
| --- | --- | --- | --- | --- |
| claude-worker | `bfc23827ee5fa47e169a7c0059414c2688d25060` | `48b68d0746779955358953103e6838c56f5ae174` | `20bca552980521f73908759d6843505ac01a3fdf` | `a7c210a51f11231d0bd087d0a01a20a047bc55eb` |
| codex-worker | `ae239552ae857294c01adcb4901fc943614ebb20` | `63b3f4b1d818147caa555f87fe3d61d88ae870fd` | `e191214a9a86c5c674dfa9e7fe7bc7004377925a` | `ef60f4d20e674e681377a67737662ceab6407191` |
| agy-worker | `f136b2aa3a13f3f0637e4d5215b37e18df35fbe8` | `4fd8004bb909eb841a1d4e57bcae5bb0c884e366` | `75bfc1f67e049d72a7e0011b54c93063ab7a144d` | `612bbe6ce7e33be9dabcb153be799c6b1b4ec193` |

Orchestrator ballot: `docs/proposals/2/ballots/orchestrator-r3-p1-ballot.md`.
Critic vote: `docs/history/votes/r3-critic-skills.md` (relocated, unedited,
from the now-deleted team-tracking directory; see decision record 015),
reproduced verbatim below.

## Context

Round 3's phases 1 and 2 ran to completion on 2026-07-21 and the round stopped
cleanly at the phase-3 boundary, blocked in part by a Gate 1 escalation. The
principal resolved that escalation on 2026-07-24 and ordered the round resumed.

**The Gate 1 blocker is closed, re-verified live by this run rather than taken
on relay**, per the issue's explicit instruction:

```
GET /suite-api/api/resources?pageSize=1           -> pageInfo.totalCount: 517
GET /suite-api/api/adapterkinds                   -> 21 adapter kinds
GET /suite-api/api/resources?adapterKind=VMWARE   -> totalCount: 169
GET /suite-api/api/resources?adapterKind=CONTAINER -> totalCount: 52
```

The delivered service account previously saw 4 objects and zero virtual
machines. It now sees 517. Two consequences run through the decisions below.
First, Gate 1 is meaningful again. Second, every payload-size and scope-control
argument that was softened by the 4-object world is back at full force:
claude-worker's measured 137,808 bytes for a **single** resource at
`maxSamples=1` now sits on top of a 517-object inventory.

## What this round measured, and why that matters more than what it argued

The three decisions below that changed a doer's mind all changed it on a
measurement taken during the round, not on an argument:

- **The auth-scheme discrepancy dissolved.** The assignment said `OpsToken`, the
  credentials file said `vRealizeOpsToken`. All three doers measured
  independently: both return 200, an arbitrary scheme returns 401, so the
  appliance holds a case-insensitive allowlist of scheme names. Record 006's
  selection of `OpsToken` stands and the alias becomes a code comment.
- **"Verb-based read-only gating is unbuildable" was asserted, then disproved by
  its own author.** claude-worker's proposal said three of four read families
  are POST, so a GET-only transport is unbuildable. claude-worker's own critique
  then measured that every Phase 1 read family has a working GET form and
  withdrew the claim in writing. agy-worker had already conceded to the false
  claim in the meantime. The correct answer turned out to be neither author's.
- **The appliance silently ignores unrecognized query parameters and returns the
  unfiltered collection with a 200.** `?identifier=<uuid>`, a plausible
  misspelling of `?resourceId=`, returns the whole collection rather than one
  object. This single measurement is what decides decision 5 below, and no
  fixture-backed test can catch the class of bug it describes.

## Decisions

Seven questions were balloted. Four ballots each: orchestrator, claude-worker,
codex-worker, agy-worker. A 3-1 or 4-0 result decides without the critic; a 2-2
invokes the critic as tiebreaker. One question split 2-2.

| # | Question | Result | Vote |
| --- | --- | --- | --- |
| 1 | Audit unavailability blocks process startup? | **No (1B)** | 4-0 |
| 2 | Audit storage format | **SQLite, no rotation (2C)** | 3-1 |
| 3 | Fixture generation | **3B, four corrections** | 3-1 |
| 4 | Retry bound | **4B, explicit per-request counter** | 4-0 |
| 5 | Read-only enforcement predicate | **5B, capability + frozen allowlist** | 4-0 |
| 5-sub | Test-only mutating capability in Phase 1? | **Yes** | 4-0 |
| 6 | Decomposition | **6B, spine with two corrections** | 4-0 |
| 6-sub | Slice owners (three main slices) | **spine/read-plane/delivery** | 4-0 |
| 6-sub | Skills owner | **agy-worker** | 2-2, **critic decided** |
| 7 | Terminal audit write failure | **7C-with-payload** | 4-0 |
| 7-sub | Escalate the invariant reading? | **No, with conditions** | 4-0 |

### Decision 1: audit unavailability does not block process startup

The process starts. `/healthz` and the admin UI stay up and report the degraded
state. MCP readiness is false and every tool call fails closed. The attempt
record remains fatal when it cannot be written.

claude-worker reversed its own proposal to vote this, and its reasoning is the
one adopted: the constitutional invariant is about tool paths, and a surface
that executes no tools is not a tool path. Refusing to boot is not a stronger
reading of the invariant, it is a rule about tool calls applied to something
that is not a tool call. What decides it operationally is the recovery path: on
a lab slot with a single operator, a full audit volume under the
refuse-to-boot design means the operator cannot reach the admin UI, cannot read
the audit log, and cannot see the reason without shelling into the host.

**Binding rider, adopted as part of the decision rather than as commentary.**
claude-worker and codex-worker arrived at this independently, in different
words. While audit is degraded, every security-relevant admin **write**
(register or edit a target, change posture, mint or revoke a key, rotate the
keyring) fails closed exactly as a tool call does. The admin UI stays available
for diagnosis and reading, never for unaudited change. claude-worker stated that
without this rider its vote is 1A instead; the decision is not recorded as
unanimous on any weaker reading.

### Decision 2: audit storage is SQLite with no automatic rotation in Phase 1

A separate SQLite database on the audit volume, distinct from the credential
store, WAL mode, bounded busy timeout. **No automatic archive rotation ships in
Phase 1.** Admission of new tool calls stops at a conservative free-space
threshold. Retention and archival are deferred to a later decision the principal
owes an answer to anyway.

This is codex-worker's storage engine with the specific mechanism agy-worker
attacked removed from the plan. The rotation procedure was the dangerous part,
not the engine: the backup-verify-delete cutover has a crash window in which
rows exist twice or not at all, and it runs against a live database on the hot
path of every tool call.

The argument that did **not** survive is the one that originally motivated
NDJSON. claude-worker's proposal argued a SQL table is the one format where
selective deletion leaves no hole; claude-worker withdrew that in the same
ballot round, verbatim: "Anyone who can delete rows can also rewrite lines."
Neither format is tamper-evident, real tamper evidence needs a hash chain or an
off-box sink, and neither is Phase 1 scope. What was described as a security
difference was a convenience difference.

On WAL: sufficient for the steady-state concern of admin UI reads concurrent
with hot-path writes, at a write rate of one or two rows per tool call at lab
concurrency. It does not rescue automatic rotation, which is why 2C and not 2B.
Nobody has benchmarked this; the decision does not rest on a benchmark, because
2C's hot path is a single short INSERT. The workplan still carries
busy-timeout, concurrent-writer, disk-exhaustion, and crash-recovery tests.

**agy-worker dissents, for 2A (NDJSON). Its objection, verbatim:**

> A SQL table makes it trivial to delete records without leaving a hole, which
> undermines the append-only guarantee. NDJSON files are harder to selectively
> edit and are easily verifiable by line count. While WAL mode reduces
> reader-writer lock contention in SQLite, the backup API rotation procedure
> still introduces a crash window and operational risk. NDJSON with app-owned
> rotation is simpler, safer, and does not compete with the credential store's
> transactions.

### Decision 3: fixtures are allowlist-projected, reference-preserving synthesis, with four corrections

No raw captured byte is ever committed. Raw captures live **outside the
repository worktree entirely**, not in a gitignored directory that `git add -f`
defeats. The generator works from an explicit allowlist of response **schema
paths**, not merely values, because object keys and URL path segments carry lab
identity. Substitution uses **deterministic pseudonyms that preserve reference
equality**, because independently replacing each occurrence of an identifier
produces a fixture in which pagination and link parsing cannot be tested at all.
A proof test asserts no raw capture token appears in generated output, and the
CI scanner backstops rather than being the primary control.

The third correction is the one worth naming: it is a correctness fix, not a
security fix, and claude-worker's ballot concedes that its own generator "would
have silently destroyed the contract it was built to preserve."

**agy-worker dissents, for 3C. Its objection, verbatim:**

> A manual recorder and generator pipeline practically guarantees fixture
> staleness. When the API drifts, the friction of manually re-running,
> re-scrubbing, and re-generating captures will encourage developers to test
> against old fixtures rather than keeping them updated. Nothing in Phase 1's
> scope solves this staleness problem, so we must explicitly accept it as an
> unsolved risk and budget nothing for it right now.

**The dissent is correct about the gap and is answered with budget rather than
argument.** 3B does not solve staleness and does not claim to. Two funded
workplan items carry it instead of an intention:

1. The tier-3 live contract run against DEVEL is a **named, budgeted workplan
   item**, run at every gate and after every appliance upgrade, not an optional
   convenience. It is the only thing that detects appliance drift and the only
   place decision 5's parameter allowlist can be validated against reality.
   claude-worker separately noted it appeared in no slice's file list; the
   workplan fixes that.
2. Every generated fixture carries **generator version, source API version, and
   generation date**, with a fixture-freshness check at the release gate.

### Decision 4: the retry bound is explicit, and target edits have drain semantics

The authentication generation counter stays: capture the generation before
issuing the request, recheck under the lock on 401, only the matching generation
re-acquires. It bounds acquisitions per storm. It does **not** bound retries per
request, and that gap was real: under mid-session credential revocation the
generation keeps moving for reasons unrelated to this request, and the caller
keeps finding a "fresh" token that also 401s.

So: an explicit **per-request retry counter** in addition to the generation
counter, making "exactly once" a checked property of the request rather than an
emergent property of the interleaving. A second 401 is a typed terminal error.
Re-auth fires on 401 only, never on 403.

Plus a separate **target-configuration generation**, checked before retry and
before returning a result, with old clients marked closed and defined
drain-or-cancel semantics on a target edit. The auth generation is single-flight
only within one live client object, and an admin edit replaces that object
underneath in-flight requests. The half that makes this more than tidiness: an
operator who flips `verify_ssl` from false to true is performing a security
action, and an in-flight request must not silently ignore it.

agy-worker found the first hole and codex-worker found the second.
claude-worker's ballot names itself the party at fault on both.

### Decision 5: enforcement is capability plus a frozen (method, path, parameter) allowlist

Two independent layers:

1. **Authorization** is semantic. Every tool declares exactly one capability at
   registration. The dispatcher checks it against the key's granted scopes
   intersected with global policy (default deny), then against target posture.
   `MUTATING` is an empty frozenset in Phase 1.
2. **The outbound contract** is a frozen per-tool allowlist of
   `(method, path template, permitted query parameter names)`, declared at
   registration, which the transport is structurally incapable of issuing a call
   outside of.

The verb carries no independent weight and cannot be the predicate.
codex-worker's own GET-only rule needs named POST carve-outs for token acquire
and release, which makes the enforced predicate `(method, path)` in an allowlist
already; a Phase 2 mutation shaped as a GET passes a verb test while bypassing
the gate, and VCF Ops has GET-shaped operations with side effects.

The parameter allowlist is not an optional extra. Because unrecognized
parameters are silently ignored and return the unfiltered collection with a 200,
a one-word typo returns record 001's token blowup with no error anywhere, and
projection does not save us because nothing is malformed: the response is
correctly shaped, correctly paginated, correctly projected, and the wrong scope.
Fixture tests structurally cannot catch it, because a mock answers whatever URL
it is handed. Validation is in the live tier.

Registration-time binding is retained from claude-worker: handlers are never
passed to FastMCP directly, the registrar generates the wrapper, and a handler
that skips the dispatcher is not an unaudited tool but a tool that does not
exist. codex-worker's correction is adopted: the private-tool-manager assertion
is a tripwire and not the security boundary, the raw FastMCP instance is not
exported to tool modules, construction and binding live in one composition root,
and an end-to-end test observes an audit record for every listed tool.

**5-sub, unanimous: both mechanisms ship.** A test-only mutating capability is
registered in a test-scoped registry and run through the **real** dispatcher
against read-only, actions-enabled, and prod fixtures, asserting deny, allow,
and deny. The production `MUTATING == frozenset()` assertion stays as a
tripwire, because its value is in diff review: adding a mutating capability then
requires deleting an assertion that says there are none. claude-worker's ballot
concedes its earlier counter was not a counter, verbatim: a branch that has
never executed "is not a tested branch, it is an untested branch with a comment
on it."

### Decision 6: three slices around an interface spine, with an open registration mapping

codex-worker's `contracts.py` interface spine, with two corrections from
claude-worker's critique:

- **The registration record is an open, versioned mapping with a small required
  core**, not a fixed signature. Otherwise a per-family declaration field (the
  metrics per-call sample cap is the concrete case) is a recurring three-way
  edit on the hottest file in the tree. Decision 5's `(method, path,
  parameters)` triple adds three fields on day one, which makes this more urgent
  rather than less.
- **Skills moves out of the delivery-surfaces slice.** Delivery as originally
  scoped was priced at 4 to 6 days and is closer to 8 to 12, and it is the slice
  Gate 1 rests on most directly.

Shared ownership of the dispatcher is rejected. codex-worker's attack 7 decides
it and claude-worker withdrew its own proposal on that reasoning: "assemble
last" leaves the integration of the most correctness-critical file in the tree
with no owner, and the only party positioned to do it is the orchestrator, which
is forbidden to write code. One resident owns the dispatcher package and
publishes narrow protocols first.

**Slice owners, 4-0 on the three main slices:**

| Slice | Owner | Contents |
| --- | --- | --- |
| Policy and persistence spine | **codex-worker** | `contracts.py`, the dispatcher package, capability and outbound-contract enforcement, migrations, encrypted target repository, versioned keyring and rotation, API keys and scope intersection, audit repository |
| VCF read plane | **claude-worker** | target client, auth and target generations, TLS, typed error hierarchy, projection and result caps, all Phase 1 read adapters, the synthetic fixture generator, contract tests |
| Delivery surfaces | **agy-worker** | app composition, MCP binding, admin UI, health and readiness, container, `ai-log-depot` CI and the docker.int deploy |
| Skills | **agy-worker** | catalog load, digest verification, index regeneration check, four render paths |

agy-worker yielded its own phase-1 claim to the target registry and credential
store in its ballot, on the merits, which dissolved the only slice collision
without requiring a ruling.

### Decision 6-sub, skills ownership: decided by the critic on a 2-2 split

agy-worker voted agy-worker (self, interest declared). codex-worker voted
agy-worker as a separately reviewable piece. claude-worker voted codex-worker.
The orchestrator voted codex-worker. **2-2, critic invoked.**

The orchestrator could have voted with the other two and closed this 3-1 without
a critic, and declined to, on the grounds that voting a position it did not hold
in order to avoid an independent check on a position it did hold is exactly what
the seat exists to prevent.

**The critic voted agy-worker, against the orchestrator and claude-worker.**
Its vote is reproduced verbatim below. The orchestrator **adopts the critic's
side** rather than holding and escalating: the distinction the critic draws
between ownership and slice absorption is sound, and the load argument does not
survive it intact.

**Critic vote, verbatim** (model transparency line included as returned; note
its own disclosure that its shell access was harness-rejected and it read the
four ballots rather than the six proposal and critique commits):

> I have the four ballots and the framed dispute. Shell/`git show` of the six
> proposal/critique commits was harness-rejected, so I'm relying on the ballots'
> restatement of critique 1.7 (especially claude-worker Q6) plus the dispatch
> framing; that is enough for this ownership question.
>
> **Model:** Composer (Cursor harness; system prompt identifies the serving
> model as Composer / Auto). Not Claude-family, not Codex, not Agy. Independence
> from both contested owners is established; I do not self-disqualify.
>
> **Vote: agy-worker**
>
> **Interest:** none (critic; non-doing seat).
>
> **Reasoning:**
>
> Both sides already agree on the hard part of 6B: skills is **out of the
> delivery slice**, as its own planned and reviewable piece. The only fight is
> whose queue that piece sits in. I am discounting the orchestrator's ballot as
> one Claude-family voice with a declared house bias, exactly as requested, and
> I am voting the argument rather than the room.
>
> The load argument for **codex-worker** is real but overstated. Critique 1.7
> (as restated in claude-worker's ballot) says delivery as originally scoped
> (`app.py`, MCP binding, admin, skills, container, CI, first docker.int deploy)
> was priced at 4-6 days and is actually 8-12, and that this is the slice Gate 1
> hangs on. That diagnosis is why everyone voted 6B. What it does **not** prove
> is that "same resident as delivery" equals "back inside the delivery slice."
> Those are different failure modes. Absorption is a workplan and review
> failure: skills rides the same estimate, the same finish line, and the same PR
> tail as Gate 1 packaging. Ownership is a staffing choice. Codex's own ballot
> draws that line correctly: skills to agy **as a separately planned and
> separately reviewable small piece, not as an implicit subdirectory of the
> delivery slice**, with an explicit redispatches if capacity requires another
> owner. That is how you keep the 1.7 rebalance without pretending calendar days
> are the only fungible resource.
>
> Gate 1 is the principal connecting a client through a reverse proxy to a
> deployed container. Skills (catalog load, digest check, four render paths) is
> not on that critical path. Moving skills onto the spine owner therefore does
> **not** de-risk Gate 1. It only lightens agy's total backlog. The cheap way to
> protect Gate 1 is sequencing and separation: delivery ships first; skills is
> its own acceptance unit and must not gate the deploy. Same-owner does not undo
> that if the workplan is honest. Different-owner only helps if skills would
> otherwise serialize ahead of Gate 1 inside one person's attention. That is a
> planning control, not a reason to force a transfer.
>
> Against parking skills on **codex-worker**: the spine is already the most
> correctness-critical slice in the round (dispatcher, credential envelope,
> keyring rotation, API keys). Skills is small and low-blast-radius, and it has
> no dependency on the store, the VCF client, or admin session state. Dumping it
> onto the lightest **day-count** slice treats risk as interchangeable with
> calendar. It is not. The spine owner should stay narrow on the protected path,
> not collect every leftover independent unit for balance optics.
>
> For **agy-worker**: adjacency is real. Skills is exposed through the MCP
> resource/prompt/tool surface that the delivery owner is already binding. A
> separate catalog module owned by the binder is a natural cut; a handoff from
> spine-owner catalog to delivery-owner mount is an extra seam for a piece
> everyone calls the smallest independent unit in the tree. I am **not** resting
> on agy's self-interested "CI pattern" line. That is a weak claim for this
> piece. The stronger agy-side evidence is Codex voting **away from itself**,
> with interest against taking more work, and writing the separation/escape-hatch
> rule into the assignment. When the proposed light-slice recipient declines the
> work and specifies how not to absorb it, that outweighs a Claude-family
> load-balancing bloc that collapses "separate piece, same owner" into "undoes
> 1.7."
>
> **Binding rider for the synthesis (not a second vote):** skills ownership by
> agy-worker is adoptable only if the workplan makes separation operational, not
> nominal: distinct workplan item, distinct review, and explicit non-blocking
> relative to Gate 1 deploy. If agy's capacity later fails that test, use Codex's
> escape hatch and redispatch. Do not silently fold skills into the delivery PR.
>
> **Losing objections preserved:** claude-worker's and the orchestrator's claim
> that same-owner undoes the 1.7 rebalance remains in the record; I reject it as
> conflating ownership with slice absorption, provided the rider above is
> written into the decision.

**The critic's rider is written into the workplan**, as its vote conditions:
skills is a distinct workplan item with distinct review, explicitly non-blocking
relative to the Gate 1 deploy, and it is redispatched to another owner rather
than silently folded into the delivery PR if agy-worker's capacity fails that
test.

**The losing objection, preserved as the critic required.** claude-worker's
position, verbatim:

> The spine slice is the smallest of the three at 4 to 6 days and delivery is
> the largest at 8 to 12, so skills goes to the light slice and not the heavy
> one. Splitting it off is the whole point of the 1.7 rebalance and putting it
> back in delivery undoes that.

### Decision 7: a failed terminal audit write returns a typed `outcome_unknown` with payload

Settled before the question and not in dispute: the **attempt** record is
written and committed before the handler runs, and its failure refuses the call.

When the **terminal** write fails after the upstream call already succeeded:

- The terminal state is `outcome_unknown`. It is neither success nor a generic
  error, and a client must branch on it rather than falling into either existing
  arm by default.
- **The result payload rides along in a subordinate field**, not in the success
  position, so a client reading only the success field sees nothing and a client
  that wants the data must acknowledge the state to reach it.
- Automatic client retry is prohibited by the contract, and the response says
  why: the upstream call completed, so a retry repeats work that already
  happened.
- Readiness goes false per decision 1. This is what makes the state safe rather
  than a loophole: the in-flight call returns its data, the next call is
  refused, and there is no window in which a stream of calls executes unaudited.
- The call is surfaced for reconciliation, with a count in `/healthz` and a list
  in the admin UI derived from **durable** storage rather than memory. When the
  store returns, `started` rows with no terminal record are closed out as
  `outcome_unknown`, never optimistically marked successful.

**Phase 1 adopts the Phase 2 shape now.** This is a return type on the choke
point, the team has spent two rounds making that file hard to change, and the
value of that is lost if its public contract is provisional. Changing a terminal
state later touches the dispatcher, every tool's response contract, the admin
UI, the reconciliation surface, and any client written against the Phase 1
shape, and doing it during the mutation round is the worst available time. The
cost is one extra terminal state that Phase 1 reads rarely reach, paid once, now,
while there are no external clients.

Unanimous, and every doer moved: codex-worker abandoned its withhold-the-result
position, claude-worker abandoned the plain-success position from its own
critique 1.4.

### Decision 7-sub: no escalation on the audit invariant, with two conditions

codex-worker raised that if the constitution's audit invariant is read as
requiring a durable **terminal** record even through physical media failure,
that is not implementable and must be escalated rather than papered over. All
four ballots voted `escalate: no`, and the reasoning adopted is claude-worker's,
because it engages the clause rather than stepping past it:

The constitution names result status among the fields that go to the durable
audit log, so the pre-execution attempt record does not on its own satisfy the
sentence literally. But no invariant can require a durable write to media that
is not accepting writes. Under decision 7 the invariant is honored as far as
physics allows and no further pretense is made: the attempt is durable before
anything happens, the outcome is explicitly typed as unknown rather than
assumed, the row is held open and closed honestly on recovery, and the server
stops accepting new work immediately. The withhold-the-result option fails the
same clause in exactly the same way, the terminal record being equally absent,
while additionally losing the caller's data. **No available option writes the
record, so the choice between them cannot be the thing the invariant governs.**

**Two conditions attached to that `no`, both adopted:**

1. This record states the interpretation in its own words, above, so that it is
   the principal's to overrule. Unwritten, the team would have decided it by
   omission, which is what the escalation rule exists to prevent.
2. It goes into the Gate 1 review packet as a named item rather than buried in a
   record. It is a one-line read and the principal may simply say yes, but he
   should say it.

## Open objections not resolved by a ballot

Recorded because they are live and because two of them are the principal's to
answer, not the team's. Both are carried into the TLDR on issue #2.

**claude-worker, on the Phase 1 reports family, verbatim:**

> **The Phase 1 reports family should be cut to nothing, or to definitions
> only.** Not on the ballot and it should have been. Record 007 makes report run
> a mutation, so Phase 1 gets listing and download. I measured
> `GET /api/reports` on DEVEL returning `totalCount: 0`: there are no
> completed report instances on that appliance. So the Phase 1 reports surface
> is a list tool that returns an empty list and a download tool that has nothing
> to download, plus a definitions tool. We would build, test, project, cap, and
> audit a family that cannot be demonstrated at Gate 1 and that no caller can
> use until Phase 2 gives it a run path. [...] I would ship report definitions
> listing only, or drop the family from Phase 1 entirely and let it land whole
> in Phase 2 alongside run.

**claude-worker, on TLS, verbatim:**

> `verify_ssl=false` is being adopted as the shipping answer by default and
> nobody voted on it. [...] The clean answer is a mounted lab CA bundle, which
> is a deployment trust-material change and therefore an escalation to Scott
> rather than a team decision. I am not proposing we block on it. I am objecting
> to it becoming the permanent answer by never being asked, and asking
> that the workplan carry it as an explicit question to Scott at Gate 1.

**codex-worker, on fingerprint pinning, verbatim:**

> Fingerprint pinning also remains underspecified. Normal certificate validation
> cannot complete a handshake against an untrusted self-signed chain and then
> perform a post-handshake fingerprint check. Phase 1 should prefer a mounted CA
> bundle. If direct fingerprint pinning remains required, the workplan must
> budget a transport implementation that verifies every connection and an
> explicit, unauthenticated first-trust ceremony.

This objection bears on claude-worker's three-state `system`/`pinned`/`insecure`
design. The workplan prefers the CA bundle and does not budget pinning.

**agy-worker, on wrong-auth-source diagnosis, verbatim:**

> As measured by Claude, a wrong auth source and a wrong password return
> byte-identical 401s. Even with the auth-source dropdown populated from
> unauthenticated endpoints, an operator who picks the wrong entry from the valid
> list will still get an unhelpful 401 error. We have no way to differentiate this
> at the API layer, meaning the operator experience for misconfigurations will
> remain poor.

Accepted as an unfixable limitation, mitigated by populating the auth-source
picker from the target's own unauthenticated `GET /api/auth/sources` at
registration time plus an explicit "Local users" entry, since the local source
does not appear in that list.

## A process note for the next run

agy-worker's phase-3 ballot re-raised the 4-object Gate 1 blocker as its scope
check, after the dispatch prompt gave it the fresh 517-object measurements at
the top of the page, and demanded an escalation that had already happened and
already succeeded. None of its six votes turns on that count and all six were
counted. It is recorded because a seat that does not update on evidence placed
directly in front of it is a thing the next run should know, and because the
issue's instruction to re-verify rather than trust the relay is what prevented
two stale inputs from going unnoticed.

## Consequences

- **Approved 2026-07-24. Implementation is authorized.** See Amendment 1.
- Implementation dispatches by slice per decision 6, after sign-offs from all
  three doers on this record and after `contracts.py` lands as the single
  planned serialization point.
- Records 001 through 008 are unchanged. Record 001's `508 resources /
  1,097,361 bytes / 92 percent projection reduction` figures were measured
  against a wider credential than the one delivered, and the re-verified
  517-object inventory makes them roughly representative again; the conclusion
  that projection is a Phase 1 requirement was never in question.

## Protected paths touched

- `src/vcf_ops_mcp/`
- `docs/SPEC.md`

## Sign-offs

    Signed-off-by: agy-worker <agy@team.local> 2026-07-24T21:58:31Z
    Signed-off-by: claude-worker <claude@team.local> 2026-07-24T22:00:03Z
    Signed-off-by: codex-worker <codex@team.local> 2026-07-24T22:05:21Z

Transcribed by the orchestrator from each worker's own signature artifact,
because the records live on a branch the workers do not write to. The artifacts
are authoritative and independently checkable, and each is copied verbatim into
`docs/decisions/signatures/` so it survives branch deletion:

| Doer | Signature artifact | Branch |
| --- | --- | --- |
| claude-worker | `92cf4a4f6c4cb40c2464a962c80af90a635211dc` | `claude/r3-signoffs` |
| codex-worker | `bebc4ac448bb9600acb98c30439ab2d241974450` | `codex/r3-signoffs` |
| agy-worker | `27f0e3c06763f5fc93fccbc09d0ad3b0adf8746e` | `agy/r3-signoffs` |

codex-worker's withholding is preserved at
`c3f392c730f472461dd4a7e9e271968f2ae91da2` on the same branch, and its signature
artifact keeps the withheld text above the signature rather than replacing it.
The withholding is part of the record: it is what produced Amendment 2.
