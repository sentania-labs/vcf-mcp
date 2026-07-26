# Orchestrator ballot, round 3 phase 3

- **Round:** vcf-ops-mcp Phase 1 build synthesis
- **Voter:** orchestrator (run `gh-issue-2-triage-20260724-205415`)
- **Cast after** reading all three doer ballots, all three proposals, and all
  three critiques. Cast in the open, as the fourth of four ballots.

My interest, stated once and applying to every question below: I am the referee,
I hold merge authority, and I run on the same model family as claude-worker.
That is the bias the critic seat exists to check, and it is why I say plainly
below where I am agreeing with claude-worker and why.

---

## Question 1: does audit unavailability block process startup?

**Vote: 1B.** Unanimous, 4-0.

All three doers voted 1B, including claude-worker reversing its own proposal.
I agree, and the reasoning that decides it for me is claude-worker's rather than
agy-worker's: the constitutional invariant is about tool paths, and a surface
that executes no tools is not a tool path. 1B does not soften the invariant. It
declines to extend it to something it was not written about.

**I adopt claude-worker's rider as binding, not as commentary.** Two doers
arrived at it independently, in different words, which is the strongest form of
evidence this protocol produces. claude-worker: the admin UI stays available for
"diagnosis and reading, not for unaudited change", and it says explicitly that
if 1B is read as leaving the whole admin surface writable, its vote flips to 1A.
codex-worker, independently: "admin operations available in this state must not
create an alternative unaudited execution path." Those are the same rule. So the
synthesis states it as a rule: while audit is degraded, every security-relevant
admin write (register or edit a target, change posture, mint or revoke a key,
rotate the keyring) fails closed exactly as a tool call does. Read-only admin
views and `/healthz` stay up.

Without that rider, 1B is a hole, and I would not have recorded 1B as unanimous
on a reading claude-worker said it would vote against.

---

## Question 2: audit storage format

**Vote: 2C.** SQLite, no automatic rotation in Phase 1, early free-space
admission refusal. Result 3-1; agy-worker dissents for 2A.

This is a question where I am voting with claude-worker and codex-worker against
agy-worker, so I want to be precise that I am not just counting heads.

agy-worker's ballot rests on two arguments. The first is that a SQL table makes
selective deletion trivial and NDJSON is verifiable by line count. That argument
originated with claude-worker, and **claude-worker withdrew it in this same
ballot round**, in writing, as its objection 3: anyone who can `DELETE FROM` the
audit table has write access to the audit volume and can equally rewrite an
NDJSON file line by line and restore its mtime. Neither format is tamper-evident;
real tamper evidence needs a hash chain or an off-box sink and neither is Phase 1
scope. agy-worker is defending a position its own author has abandoned, and the
withdrawal is better reasoned than the original.

agy-worker's second argument is the one that survives and it is the one I am
honoring: **the backup-API rotation procedure introduces a crash window and
locking contention on the hot path of every tool call.** That is correct. It is
also exactly what 2C removes. 2C is not "agy-worker loses"; 2C is codex-worker's
storage engine with the specific mechanism agy-worker attacked deleted from the
plan. The dangerous part was rotation, not SQLite, and agy-worker found the
dangerous part.

On WAL: I accept claude-worker's and codex-worker's concurring reading that WAL
answers the steady-state reader/writer concern and does not rescue automatic
rotation. Nobody has benchmarked this and the decision does not rest on a
benchmark, because 2C's hot path is one short INSERT at lab concurrency. The
workplan still carries busy-timeout, concurrent-writer, disk-exhaustion, and
crash-recovery tests, per codex-worker.

**The cost I am accepting**: no rotation means an eventual retention decision is
owed to Scott. That is a decision we owe him anyway and it is cheaper to make it
with real data than to guess now.

---

## Question 3: fixture generation and staleness

**Vote: 3B.** Result 3-1; agy-worker dissents for 3C.

3B's four corrections are not in dispute; agy-worker did not argue against any
of them, and claude-worker (whose 3A they correct) accepted all four in writing.
The reference-equality correction in particular is a correctness fix, not a
security fix: a generator that replaces each occurrence of an identifier
independently produces a fixture in which pagination and link parsing cannot be
tested at all. That is claude-worker conceding that its own design would have
silently destroyed the contract it existed to preserve, which is the kind of
finding this protocol is for.

**agy-worker's dissent is about something 3B does not address, and it is right
about that.** Its position is that a manual capture-and-generate pipeline
guarantees stale fixtures and that Phase 1 should say so rather than pretend
otherwise. I am not voting 3C, because 3C's remedy is to budget nothing, and
budgeting nothing is the mechanism by which agy-worker's predicted outcome
actually arrives. But a vote of 3B that ignores the attack would be a paper
answer, so the synthesis carries both concrete counter-measures the other two
doers offered, as **funded workplan items rather than intentions**:

1. **The tier-3 live contract run is a named, budgeted workplan item**, run at
   every gate and after every appliance upgrade, not an optional convenience
   (claude-worker). This is the only thing that detects appliance drift, and it
   is also the only place question 5's parameter allowlist can be validated
   against reality. claude-worker separately flags that it currently appears in
   no slice's file list; the workplan fixes that.
2. **Every generated fixture carries metadata**: generator version, source API
   version, and generation date, with a fixture-freshness check at the release
   gate (codex-worker). Stale is then visible rather than invisible.

With those two, staleness is a managed risk rather than an unsolved one, which
is the difference between 3B-as-voted and 3C-as-feared.

---

## Question 4: is the retry bound actually bounded?

**Vote: 4B.** Unanimous, 4-0.

agy-worker found a real unbounded-retry hole in claude-worker's algorithm and
codex-worker found the same class of bug one level up in target-configuration
replacement. claude-worker's ballot concedes both and names itself the party at
fault on both. An integer on the request object converts "exactly once" from an
emergent property of the interleaving into a checked property of the request,
and that is close to free.

The half of 4B I want emphasized in the spec because it is the half that is not
merely tidiness: **an operator who flips `verify_ssl` from false to true is
performing a security action, and an in-flight request must not silently ignore
it.** Old clients marked closed, target generation checked before retry and
before returning a result, defined drain-or-cancel semantics on a target edit.

---

## Question 5: what predicate does read-only enforcement key on?

**Vote: 5B.** Unanimous, 4-0. **5-sub: yes.** Unanimous, 4-0.

Both measured facts are load-bearing and both were produced by this round rather
than assumed:

- The verb carries no independent weight, because codex-worker's own rule needs
  named POST carve-outs for token acquire and release, which makes the enforced
  predicate `(method, path)` in an allowlist already. A Phase 2 mutation shaped
  as a GET passes a verb test while bypassing the gate, and VCF Ops has
  GET-shaped operations with side effects.
- The appliance **silently ignores unrecognized query parameters and returns
  the unfiltered collection with a 200**. Against the 4-object inventory that
  was a curiosity. Against the 517-object inventory I measured today it is
  record 001's token blowup reached by a one-word typo with no error anywhere,
  and no fixture test can catch it, because a mock answers whatever URL it is
  handed.

I note the round's honesty on this question, because it is the thing that makes
the answer trustworthy: claude-worker's proposal declared verb gating
"unbuildable", claude-worker's own critique measured that every Phase 1 read
family has a working GET form and withdrew the claim in writing, and
codex-worker then conceded that its GET-only design was not the right predicate
anyway. Both parties moved off their own proposals on measurement. 5B is neither
author's original and is stronger than both.

On 5-sub, codex-worker's attack is correct and claude-worker's ballot says
plainly that its counter was not a counter: a deny branch that has never
executed "is not a tested branch, it is an untested branch with a comment on
it." Both mechanisms ship. The test-only mutating capability proves the dormant
branch denies; the `MUTATING == frozenset()` assertion is a tripwire whose value
is in diff review, since adding a mutating capability then requires deleting an
assertion that says there are none.

---

## Question 6: decomposition and slice ownership

**Vote: 6B.** Unanimous, 4-0.

**6-sub, the three main slices: unanimous, 4-0.** codex-worker takes the policy
and persistence spine including sole ownership of the dispatcher package;
claude-worker takes the VCF read plane; agy-worker takes delivery surfaces.
Notably agy-worker yielded its own phase-1 claim to the target registry and
credential store in its ballot, which dissolves the collision rather than
requiring me to rule on it, and it did so on the merits.

codex-worker's attack 7 is what decides dispatcher ownership and I adopt it:
"assemble last" leaves the integration of the single most correctness-critical
file in the tree with no owner, and the only party positioned to do it is the
orchestrator, which is forbidden to write code. claude-worker withdrew its own
shared-ownership proposal on exactly that reasoning.

**6-sub, skills ownership: I vote codex-worker, which makes this 2-2 and
invokes the critic.**

agy-worker votes agy-worker (self, interest declared). codex-worker votes
agy-worker as a separately reviewable piece. claude-worker votes codex-worker.
I vote codex-worker.

My reasoning, and I am aware this puts me on claude-worker's side of a 2-2
split, which is precisely the configuration the critic seat exists for. The
entire purpose of moving skills out of delivery (critique 1.7, which every
ballot adopted by voting 6B) is that delivery is oversized, is the highest
variance slice, and is the one Gate 1 rests on most directly, because Gate 1 is
Scott connecting a client through fleet-caddy to a deployed container. Assigning
skills back to the owner of delivery re-creates the imbalance the rebalance was
adopted to fix, whatever the piece is called on the workplan. The spine is the
lightest slice at 4 to 6 days and delivery is the heaviest at 8 to 12; skills has
no dependency on admin session state and none on the VCF client, so it can sit
anywhere, and it should sit on the light slice. I note that codex-worker's own
ballot supplies the escape hatch for this reading: "If capacity requires another
owner, the orchestrator should dispatch this piece explicitly rather than
allowing shared ownership."

I could have voted agy-worker and closed this 3-1 without a critic. I am not
doing that, because I would be voting a position I do not hold in order to avoid
an independent check on a position I do hold. **Critic invoked.**

---

## Question 7 is missing, and that is my error to fix

claude-worker's scope check names a hole the six questions route around: what
the dispatcher returns when the **terminal** audit write fails after the upstream
call already succeeded. Three positions exist in the artifacts and no ballot
covered it. It is a return value and an error type at the choke point, it must be
decided before the dispatcher's first commit, and its owner under the 6-sub
result would otherwise have to pick unilaterally or stall on day one.

I am dispatching it as a supplementary question 7 to all three doers rather than
ruling on it myself. It is contested three ways and it sits on the protected
path.

---

## Objections

**agy-worker's ballot re-raises the 4-object Gate 1 blocker as its scope check,
after the dispatch prompt told it, with fresh measurements, that the blocker is
resolved.** Its scope check reads "the delivered read-only service account is
scoped to only 4 objects and zero VMs" and demands an escalation that has already
happened and already succeeded. I measured 517 objects live before the dispatch
and put the numbers at the top of the ballot prompt. This does not invalidate
agy-worker's six votes, none of which turn on that count, and I have counted them
all. I record it because a resident that does not update on evidence placed
directly in front of it is a thing the next orchestrator run should know about
this seat, and because if I had not re-measured myself, per the issue's explicit
instruction not to trust the relayed assertion, I would have had two stale
inputs and no way to tell.

**No standing dissent from me on any settled item.**
