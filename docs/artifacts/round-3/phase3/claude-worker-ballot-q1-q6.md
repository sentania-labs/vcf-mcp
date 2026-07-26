---
source-ref: 20bca552980521f73908759d6843505ac01a3fdf
source-commit: 20bca552980521f73908759d6843505ac01a3fdf
source-blob: 60c9757d6ae16ee3c907b65e173db9dab7c549a7
source-path: docs/proposals/claude-worker-r3-p1-ballot.md
worker: claude-worker
round: round-3
phase: phase3
captured: 2026-07-26
---

# Round 3 phase 3 ballot, claude-worker

- **Round:** vcf-ops-mcp Phase 1 build synthesis
- **Author:** claude-worker
- **Artifacts read:** all six, at the SHAs named in the dispatch.
- **Recon:** none taken this phase. Nothing below turns on a fact the
  orchestrator has not already measured and recorded.

Two of my six votes go against my own proposal. Both are marked.

---

## Question 1: does audit unavailability block process startup?

**Vote: 1B.**

**Interest: I proposed 1A (my proposal 1.7). This is a reversal.**

My argument for 1A was that an outage saying "the audit volume is full" is a
good outage, and that softening an unconditional constitutional invariant is an
escalation rather than a code comment. The first half is still true. The second
half does not apply, and I was wrong to claim it did.

The invariant is that no tool path ships without its audit write. 1B does not
touch a tool path. Under 1B every tool call fails closed, MCP readiness is
false, and the attempt record is still fatal when it cannot be written. The
invariant is fully intact. What stays alive under 1B is a surface that executes
no tools. Refusing to boot is not a stronger reading of the invariant, it is a
stronger reading of a rule about tool calls applied to something that is not a
tool call.

What decides it is the recovery path. This is a container on a lab slot with a
single operator. Under 1A, a full audit volume means the operator cannot reach
the admin UI, cannot read the audit log, cannot change a target posture, and
cannot see the reason without shelling into docker.int and reading container
logs. Under 1B the operator opens the UI and the page says the audit volume is
full. Both are outages. 1B is the one that tells you what happened in the place
you would look.

**Rider, and I want this in the record rather than assumed:** admin operations
that change security-relevant state (registering or editing a target, changing
posture, minting or revoking a key, rotating the keyring) must also fail closed
while audit is degraded. Those are audited events too, and a mode where the MCP
surface is frozen but a human can silently re-posture a target through the UI
would be a real hole. 1B keeps the UI available for **diagnosis and reading**,
not for unaudited change. If the team reads 1B as leaving the whole admin
surface writable, my vote is 1A instead, because that version does soften the
invariant.

---

## Question 2: audit storage format

**Vote: 2C.** SQLite, no automatic rotation in Phase 1, early free-space
admission refusal.

**Interest: I proposed 2A (NDJSON). My critique 1.5 already recommended 2C.
This is a reversal, and it was made in writing before this ballot.**

I withdraw the load-bearing half of my own 2A argument. I wrote that a SQL table
is the one format where selective deletion leaves no hole, and that NDJSON is
verifiable by size and line count. That comparison does not survive contact with
the threat model. An actor who can `DELETE FROM audit_events` has write access
to the audit volume, and that same actor can rewrite an NDJSON file line by line
and restore its mtime. Neither format is tamper-evident. What I was actually
describing was a difference in convenience, not in security, and I dressed it up
as the latter. Real tamper evidence needs a hash chain or an off-box sink, and
neither is in Phase 1 scope.

With that argument removed, codex's reasons stand unopposed: one transactional
model, atomic revocation in the same store idiom, and an admin UI that can query
the audit log without somebody first writing an NDJSON reader. That reader is
work I did not price in my proposal and it lands in the delivery slice, which is
already the oversized one.

**On agy's locking attack, and whether WAL answers it.** WAL is sufficient for
the *steady-state* concern, which is admin UI reads concurrent with hot-path
audit writes. WAL readers do not block the writer and the writer does not block
readers, and the write rate here is one or two rows per tool call at lab
concurrency. That part of agy's attack does not survive WAL.

What WAL does **not** answer is the specific thing agy pointed at, the backup
API running against a live database on the hot path, plus the crash window in
the backup/verify/delete cutover where rows exist twice or not at all. That is
why I vote 2C and not 2B. Rotation is the dangerous part, not the storage
engine, and Phase 1 does not need rotation: this is a lab appliance with one
operator and no automated tool traffic, so audit growth over a Phase 1 lifetime
is small. Removing rotation removes the entire failure class that agy correctly
identified, and it costs an eventual retention decision that we owe Scott
anyway. Nobody has benchmarked this and my vote does not depend on a benchmark,
because 2C's hot path is a single short INSERT.

---

## Question 3: fixture generation and staleness

**Vote: 3B.**

**Interest: 3A is my proposal section 5. 3B is 3A plus four corrections from
codex's attack 4, all of which I accept.**

All four corrections are right, and the second and third are the ones that
matter most:

- Captures outside the worktree. A gitignored directory is a convention, and
  `git add -f` beats a convention. Correct.
- Schema-path allowlist, not just value allowlist. Object keys and URL path
  segments carry lab identity, and my generator was value-focused. Correct, and
  it is the leak my design would actually have produced.
- Deterministic pseudonyms preserving reference equality. This one is a
  correctness fix, not a security fix, and it fixes something my design broke.
  A resource identifier appears in the resource object and again in its links.
  Replacing each occurrence independently produces a fixture where identity and
  link parsing cannot be tested at all, which defeats the purpose of having a
  structurally faithful fixture. My generator would have silently destroyed the
  contract it was built to preserve.
- Proof test that no raw capture token appears in generated output. Cheap,
  mechanical, and it converts the CI scanner from the only control into the
  second control.

**On staleness, and I am answering agy directly rather than around it: nothing
in the fixture pipeline solves staleness, and 3B does not claim to.** agy is
right that manual re-capture friction produces stale fixtures. But the fix for
staleness is not a better fixture generator, it is a live tier: the tier-3
opt-in `pytest -m live` run against DEVEL is what detects that the appliance
drifted, and a stale fixture is harmless as long as something independently
checks reality on a schedule. So the answer to agy is that the live tier must
be a budgeted, named workplan item run at every gate and after every appliance
upgrade, not an optional convenience. If we ship 3B without funding the live
tier, agy's attack lands in full and we will not know it for months.

I do not vote 3C, because 3C accepts staleness as unsolved *and budgets nothing*,
which is exactly the outcome agy predicted.

---

## Question 4: is the retry bound actually bounded?

**Vote: 4B.**

**Interest: I wrote the generation-counter algorithm and asserted "retry
exactly once" without carrying per-request state. agy found the gap in my
design and codex found the target-configuration half. I am the party at fault
on both.**

The generation counter is a property of the *interleaving*, not of the request.
It guarantees that N callers hitting one expired token produce one acquisition.
It does not guarantee that any individual caller retries once, because the
caller's retry decision reads shared state that another caller can move again
between the failure and the recheck. Under credential revocation mid-session
the generation keeps moving for reasons unrelated to this request, and the
caller keeps finding a "fresh" token that also 401s. agy's loop is real.

An integer on the request object is close to free and turns "exactly once" from
an emergent property into a checked one. There is no argument for 4A other than
minimalism, and minimalism is not worth an unbounded loop against an appliance.

Codex's target-configuration generation is the same class of bug one level up
and I accept it on the same reasoning: the auth generation is scoped to one live
client object, an admin edit replaces that object, and in-flight requests keep
using superseded credentials and superseded TLS policy against a target the
operator believes they just changed. The TLS half is the part that makes this
more than tidiness. An operator who flips `verify_ssl` from false to true is
performing a security action, and it must not be silently ignored by requests
already in flight. Old clients marked closed, generation checked before retry
and before returning a result, defined drain semantics on edit.

---

## Question 5: what predicate does read-only enforcement key on?

**Vote: 5B.** Capability registry plus a frozen per-tool allowlist of
`(method, path template, permitted query parameter names)`.

**Interest: I proposed 5A, and I proposed it on a false premise. My critique 0.1
measured that every Phase 1 read family has a working GET form and withdrew the
"unbuildable" claim in writing. 5B is my critique section 4 item 1.**

Both measured facts point the same way and I will take them in order.

**The verb carries no independent weight.** Codex's rule is not "GET". It is
"GET plus the token acquire and release paths", and those carve-outs are POSTs
that create and destroy server-side session state. The moment a rule needs
named exceptions, the enforced predicate is `(method, path)` in an allowlist and
the verb is a naming convention for the common case. That is fine as a
convention and useless as a guarantee. The concrete failure is Phase 2's first
GET-shaped operation with a side effect, and VCF Ops has those in its report and
task surfaces: the registry test asserting "declared verbs are GET" stays green,
`request_read()` accepts the call, and the mutation gate is bypassed without
anyone editing the gate. 5C's proof proves the convention, not the property.

**The parameter allowlist is not an optional extra.** This appliance silently
ignores unrecognized query parameters and returns the unfiltered collection with
a 200. `?identifier=<uuid>`, a plausible misspelling of `?resourceId=`, returned
the whole collection rather than one object. Against 4 objects that was a
curiosity. Against 517 it is record 001's token blowup reached by a one-word
typo with no error anywhere, and projection does not save us because nothing is
malformed: the response is correctly shaped, correctly paginated, correctly
projected, and the wrong scope. Fixture tests structurally cannot catch it,
because the mock answers whatever URL it is handed. The only place this can be
caught is a declared, frozen list of parameter names the tool is permitted to
send, checked at least once against the live appliance.

So: capability and posture at the dispatcher, `(method, path template, permitted
parameters)` frozen at registration and enforced at the transport, and a
transport that is structurally incapable of issuing a call outside the frozen
set. Codex was right that the transport must be structurally incapable and I was
wrong to leave the transport ungated. Codex was wrong about which predicate. 5B
is the merge, and it is strictly stronger than either input.

I note that 5B costs something real: every tool now declares four things instead
of one, and the frozen set is another field on the registration record. That is
precisely why question 6's open versioned mapping matters, and the two votes
should be read together.

**5-sub: yes.**

Codex's attack 6 is correct and my counter was not actually a counter. Asserting
`MUTATING == frozenset()` proves Phase 1 declares no mutation. It proves nothing
about whether a mutation would be denied, because the deny branch never
executes. A branch that has never once run is not a tested branch, it is an
untested branch with a comment on it. Phase 2's first mutation would both
activate and test the choke point, which is how a gate turns out to have been
inverted the whole time.

These are not mutually exclusive and both should ship. Register a test-only
mutating capability in a test-scoped registry and run it through the *real*
dispatcher against read-only, actions-enabled, and prod fixtures, asserting deny,
allow, and deny respectively. Keep the production `MUTATING == frozenset()`
assertion as the tripwire, because its value is in the diff review rather than
in the test run: adding a mutating capability should require deleting an
assertion that says "there are none", which is a visible and greppable act. The
test-only capability lives in the test tree and does not weaken that.

---

## Question 6: decomposition and slice ownership

**Vote: 6B.**

**Interest: 6B is codex's structure with my critique 1.6 and 1.7 corrections
applied. I proposed 6C and I withdraw it.**

I withdraw 6C on codex's attack 7, which is correct. "Assemble `dispatch.py`
last against interfaces" means the integration of the single most important file
in the tree has no owner, and the only party positioned to do it is the
orchestrator, which is forbidden to write code. I named this seam as my own
proposal's weakest point (2.6) and then proposed shared ownership of it anyway.
One resident owns the dispatcher package and publishes narrow protocols first.

The two corrections in 6B are both about the same failure, which is a plan that
budgets one barrier and gets five:

- **Open versioned registration mapping, not a fixed signature.** `contracts.py`
  is called the only planned serialization point. It will not be, because slice
  2 keeps discovering declaration fields slice 1 must accept. The metrics sample
  cap is the concrete case: metrics needs a per-call cap that inventory does
  not. With a fixed signature that is a three-way edit on the hottest file, and
  it recurs. With an open mapping carrying a small required core it is an
  additive adapter change plus a dispatcher reader. Question 5's `(method, path,
  parameters)` triple makes this more urgent, not less, since it adds three
  fields on day one.
- **Skills moves out of delivery.** Delivery as codex scoped it is `app.py`,
  `mcp_server.py`, all of `admin/`, templates, skills, Dockerfile, compose, and
  the build-deploy workflow, priced at 4 to 6 days. Record 004's admin hardening
  alone is nine requirements including recent-reauth, which needs its own state
  and its own tests. Record 005's skills surface is a catalog, a digest check,
  and four distinct exposures. First deploy through the docker.int slot is
  high-variance work nobody here has done. That is 8 to 12 days, not 4 to 6, and
  it is the slice Gate 1 depends on most directly, because Gate 1 is Scott
  connecting a client through fleet-caddy to a deployed container. Codex's own
  mitigation, ship admin and MCP first and let CI follow, defers the long pole,
  which is how a tail becomes the schedule.

**6-sub: assignment.**

- **codex-worker: policy and persistence spine.** Migrations, encrypted target
  repository, versioned keyring and rotation, API keys and scope intersection,
  the audited dispatcher package, and the mutation choke point. Record 003
  already assigned it the envelope and rotation state machine, its
  length-prefixed AAD and HMAC digest beat mine and I conceded both in writing,
  and its schema carried an optimistic revision column and FQDN normalization
  that mine lacked. It also owns the dispatcher outright, per its own attack 7,
  which I accept. This resolves the codex/agy collision in codex's favor.
- **claude-worker (me): VCF read plane.** `vcf/client.py`, token lifecycle, TLS,
  the typed error hierarchy, projection, and the read adapters. The claim is not
  general competence, it is that the four constants this layer is built on (the
  scheme allowlist, the 6-hour TTL with independent tokens, the 401/403 split
  with its JSON/HTML body inconsistency, and the silent-parameter-ignore
  behavior) I measured myself, and handing the layer to someone who has to
  either re-run that recon or trust my table is how a subtly wrong constant
  lands underneath everything else. Record 006 already defined this file's
  contract and record 007's per-family fingerprints are computed over responses
  this layer parses. I continue to explicitly decline the store.
- **agy-worker: delivery surfaces.** `app.py`, `mcp_server.py`, `admin/`,
  templates, container, CI, and deploy. agy is the only one of the three who
  wrote the `ai-log-depot` CI path concretely, and record 007 already identified
  correct-by-checklist implementation of a specified surface as its stated
  strength, which is exactly what record 004's hardening list is. This is
  unclaimed territory that agy is best placed to take, and it settles the
  collision without leaving a gap.
- **Skills: codex-worker, as a small second piece.** Skills is a catalog load, a
  digest verification, an index regeneration check, and four render paths. It has
  no dependency on admin session state, no dependency on the VCF client, and it
  is the smallest independent unit in the tree. The spine slice is the smallest
  of the three at 4 to 6 days and delivery is the largest at 8 to 12, so skills
  goes to the light slice and not the heavy one. Splitting it off is the whole
  point of the 1.7 rebalance and putting it back in delivery undoes that.

**What I am claiming that I did not claim in phase 1:** the seed content for the
suite-api auth walkthrough skill (SPEC 4.2), authored by me and handed to
codex-worker's skills plumbing. Section 0 of my proposal is the most accurate
description of that appliance's auth behavior this team has, and it should be
the skill rather than sitting in a proposal nobody reads after this round. That
is content authoring, a day at most, and it does not make me a co-owner of the
skills piece.

---

## Objections

**1. The Phase 1 reports family should be cut to nothing, or to definitions
only.** Not on the ballot and it should have been. Record 007 makes report run a
mutation, so Phase 1 gets listing and download. I measured
`GET /api/reports` on DEVEL returning `totalCount: 0`: there are no completed
report instances on that appliance. So the Phase 1 reports surface is a list
tool that returns an empty list and a download tool that has nothing to
download, plus a definitions tool. We would build, test, project, cap, and audit
a family that cannot be demonstrated at Gate 1 and that no caller can use until
Phase 2 gives it a run path. Codex's own risk list separately flags that binary
report download through MCP may be unusable regardless. I would ship report
definitions listing only, or drop the family from Phase 1 entirely and let it
land whole in Phase 2 alongside run. The days saved are better spent on the
delivery slice, which is the one Gate 1 actually rests on.

**2. `verify_ssl=false` is being adopted as the shipping answer by default and
nobody voted on it.** The settled list fixes per-target TLS configuration on
that target's own client, which is right and which I do not contest. It does not
settle what value we ship for DEVEL. Two of us measured that DEVEL's certificate
does not validate against the host trust store, so the honest first registration
is `verify_ssl=false`, and codex is right that this exposes credentials and
tokens to anyone on that network segment. The clean answer is a mounted lab CA
bundle, which is a deployment trust-material change and therefore an escalation
to Scott rather than a team decision. I am not proposing we block on it. I am
objecting to it becoming the permanent answer by never being asked, and asking
that the workplan carry it as an explicit question to Scott at Gate 1.

**3. A correction to my own critique, recorded so the reasoning is not reused.**
My critique 1.5 argued that NDJSON's resistance to selective deletion was a
security property that SQLite lacked. It is not. Anyone who can delete rows can
also rewrite lines. I voted 2C partly against my own prior argument and the
prior argument should not be cited by anyone later as a reason to revisit.

---

## Scope check

**Yes, there is a hole, and it is one the six questions route around rather than
close: what happens when the terminal audit write fails after the upstream call
already succeeded.** Question 1 settles process startup and the settled list
settles that the attempt record is fatal, but the tail is an open three-way
disagreement. Codex withholds the result and returns `audit_unavailable`. I
argued in critique 1.4 that withholding buys nothing, since the read already
happened, the `started` row already names who called what against which target,
and the caller can simply call again, so the only effect is data loss for the
user. Codex's attack 2 raises a third position I did not answer, that the honest
terminal state is `outcome_unknown` and that automatic retry must be prohibited,
which matters little for Phase 1 reads and matters enormously for Phase 2
mutations where a retry can double-submit. This is not a philosophical question.
It is a return value and an error type in the dispatcher, it must be decided
before the dispatcher's first commit, and its owner (codex-worker under my 6-sub
vote) would otherwise have to either pick unilaterally or stall on day one. It
needs a directive or a fourth ballot question, and it is cheap now and expensive
in a week.

Two smaller items that do not rise to holes but should be in the workplan as
day-one spikes rather than discovered mid-build. First, FastMCP identity
injection: all three designs assume the API-key identity resolved in ASGI
middleware is available inside the tool handler, agy made it its one-hour
question, and none of us has verified it. If it does not work as assumed, every
audit record and every authorization check in all three proposals rests on an
identity that is not there at the point of use. It is an afternoon to prove and
it gates the dispatcher. Second, the live tier from question 3: it is the only
thing that answers agy's staleness attack and the only place the parameter
allowlist from question 5 can be validated against reality, and it currently
appears in no slice's file list.
