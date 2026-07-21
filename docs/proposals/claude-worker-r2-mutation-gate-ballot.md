# claude-worker, round 2, phase 3 ballot

- **Worker:** claude-worker
- **Branch:** `claude/r2-mutation-gate`
- **Written:** 2026-07-21T17:39:24Z
- **Read for this ballot:** all six artifacts named in the phase 3 dispatch.

## Q1

**Vote:** (a)

**Interest:** I am voting against my own phase 2 position. I proposed (a) in
phase 1, withdrew it for (b) in my critique, and I am now returning to (a).
codex-worker's critique argued for (a) and I am agreeing with it.

**Reasoning:** What decides it is attribution, and my withdrawal rested on half
a fact. I withdrew the cap because the documented 200 response to
`POST /api/alerts` is an `alerts` array of per-alert records keyed by
`alertId`, so per-alert readback looked native. It is native *for successes*.
The documented example shows only successes, and the spec documents whole
request 200 and 500 and nothing in between. So the shape I relied on tells me
which alerts came back, not which alerts the verb actually took effect on, and
codex is right that a returned object establishes that a response arrived, not
causation by this request. At N=1 that ambiguity disappears entirely: whatever
the response is, terminal, empty, or a 500, it is unambiguously about the one
alert the operator confirmed. At N greater than 1 with an undocumented
failed-member representation, the server can record a failed alert as
succeeded, which is an audit-correctness defect and not merely a UX one.

agy-worker's workflow objection is real and I do not think (a) is right
forever. It is right for MVP at zero cost, because no alert verb is grantable
in MVP anyway under the settled list, so the cap constrains nothing that ships.
The record should therefore write the cap as an MVP boundary tied to a named
unknown rather than as a design principle, and say that the bound moves to a
number the moment the unknown is measured.

**Fact that would change my vote:** how a failed member of a bulk
`POST /api/alerts` request is represented in the 200 body. If a failed alert is
distinguishable per-ID, (b) becomes correct immediately and I would vote for it
with the bound written as a number. This cannot be measured without mutating,
so it belongs to the Phase 2 gate alongside Q2's question.

## Q2

**Vote:** (c)

**Interest:** (c) is closest to my own critique's position 4, where I
downgraded the action revalidation source from a claim to an open question and
called it the single highest-value question for the Phase 2 gate. I am voting
against agy-worker's changed position, which was aimed partly at my proposal.

**Reasoning:** The three options differ in where they put an unresolved fact.
(a) puts it in a risk register and ships the code anyway, which means the
highest-blast-radius family's freshness check is a POST we have guessed is
safe. Writing "unproven" next to a call does not make issuing it safer; it
makes the eventual incident well-documented. (b) is the one I take most
seriously, because agy is right that populate can carry dynamic defaults and
that strict digest equality against a drifting response produces false
refusals, and false refusals train operators to stop reading refusals, which I
argued myself in round 1. But (b) answers the external review's finding by
declining to fix it for the only family where it was found. The finding was
that a stale plan could execute a destructive action. Cached-definition
comparison cannot detect a defaults change, because I measured that
`GET /api/actiondefinitions` carries no parameter metadata at all: 142
definitions, keys `actionAdapterKindKey, canRecommend, contextAdapterKindKey,
contextIds, contextResourceKindKey, displayName, id, scheduleEnabled, type`.
So (b) is not a weaker freshness check for actions, it is close to none.

(c) is cheap for exactly the reason the dispatch names. Actions are already
ungrantable until the Phase 2 gate under record 001 and Scott's ruling 2, so
"action apply does not ship until this is answered" removes nothing from MVP.
It also converts an open risk into a blocking question with an owner and a
deadline, which is the difference between a risk we manage and a risk we have
written down. And it keeps the general rule uniform: every family revalidates
before apply, with the action family's source named and its safety pending.

**Fact that would change my vote:** whether `POST /api/actions/{id}/query` is
side-effect-free and byte-stable across repeated calls with identical input. If
it is proven safe and stable, (c) resolves into (a) minus the risk. If it is
proven to mutate or to drift, (c) resolves into (b) plus an honest statement
that actions have no live revalidation source, and the team then has to decide
whether an action family with no freshness check ships at all. Either way (c)
is the option that makes the answer decide the design rather than the reverse.

## Q3

**Vote:** (b)

**Interest:** (b) is my own proposal from critique section 1b objection 6. I
raised it against codex only because codex invited it, and I note that it
defeats my own phase 1 signature harder than it defeats codex's: my
`plan_mutation(target_id, operation, subject: object)` passed an opaque nested
object, which is the worst of the three shapes for the client in question.

**Reasoning:** What decides it is that (c) splits the gate along the wrong
seam. Plan time is where the posture snapshot, the scope resolution, and both
fingerprints are computed. Typed per-family planners duplicate the half of the
gate that carries the security content and share only the half that is a state
transition. A security boundary implemented three times is three chances to
implement it differently, and that cost is paid whether or not the client
problem turns out to be real. Between (a) and (b), flat optional scalars are
the lowest-variance shape across tool-calling clients, they degrade into
something a weak client can still populate, and the closed discriminator
survives because the server rejects any field not belonging to the named
operation.

**Since nobody has run the test, what the record should do in the meantime:**
separate the normative clause from the presentational one. The record should
state as binding that the server validates the full field set against the named
operation and refuses any field outside it, regardless of what the client sent
or how it rendered the schema. It should state the flat-scalar shape as the
default presentation, revisable without a new decision record if the Private
AI Services render test says otherwise. That way a client that renders the
schema badly produces a refusal rather than a wrong mutation, and the test can
change the shape later without reopening the security clauses. The test itself
should be a named Phase 2 gate item, not a background hope.

**Fact that would change my vote:** a render-and-validate test of the nested
union against VCF Private AI Services and Claude Desktop. If both handle the
union cleanly, (a) is better than (b) on input contract quality and I would
switch. If either fails on it, (b) stands.

## Q4

**Vote:** (a) for `report:run`. Defer `report:publish`, which is a separate
scope and I vote differently on it.

**Interest:** the shallowness of the report fingerprint is my own critique's
objection 4 against codex, and I said there that it hits my proposal
identically. I am voting for the option I named there as the one I would take.

**Reasoning:** codex's rule, that a family without a safe readback contract does
not implement the operation, is a good rule aimed at blast radius, and the
question is whether `report:run` is the kind of operation it was written for.
It is not. A stale report definition produces a report whose content differs
from what the operator previewed. Nothing on the monitored estate changes, no
alert state moves, no VM is touched. The failure mode of a shallow fingerprint
here is a wrong document, and a wrong document is legible after the fact in a
way a wrongly executed action is not. Measured, the check is genuinely shallow:
`GET /api/reportdefinitions/{id}` on 9.0.2 returns exactly `active,
description, id, links, name, owner, subject, traversal-specs`, no version, no
timestamp, no content hash, and definition content is largely carried by
referenced views this endpoint does not project. So (a) is only acceptable if
the record states plainly, in the record and in the operator-facing summary,
that the check binds definition *identity* and cannot detect content drift.
Deferring instead would cost us the family for an unknown period and buy
protection against a low-harm failure.

`publish: true` is a different operation wearing the same endpoint. It is
tenant-visible, which is an outward-facing side effect with an audience that
did not confirm anything, and the shallow fingerprint means we could publish
content the operator did not preview to people the operator cannot recall it
from. That earns codex's rule. `report:publish` stays ungranted, and
`plan_mutation` refuses `publish: true` server-side in MVP rather than merely
not granting the scope, so the refusal does not depend on scope configuration
being right.

**Fact that would change my vote:** any 9.0.x readback that exposes
report-definition content drift, including a view-level revision the definition
read could project. I looked and did not find one. If one exists, (a) stops
being shallow and the caveat comes out of the record.

## Objections

Three, none of them a request to reopen a settled item.

1. **The four questions do not ask whether the ownership verbs are revalidatable
   at all.** Measured on DEVEL, no alert of 1124 returns `ownerId` or
   `ownerName`, though the 9.1 schema declares both, and `controlState` is
   `OPEN` for all 1124. If ownership only becomes readable once an alert is
   owned, we cannot know without taking ownership, which is a mutation. If it
   never becomes readable, then `alert:takeownership`, `alert:releaseownership`,
   and `alert:assignownership` have no observable freshness signal, and under
   the settled rule that every family revalidates before apply, they are not
   implementable rather than merely deferred. The record should say that
   explicitly instead of leaving three verbs in a scope table that quietly
   cannot satisfy the gate. This is a Phase 2 gate question of the same kind as
   Q2's.

2. **The payload-submission question is unsettled and not on the ballot.** My
   critique's strongest objection to codex was that "the submit payload is the
   newly validated effective payload, never blindly the stored bytes"
   contradicts codex's own principle that confirmation belongs to the exact
   payload the operator saw, because a canonical digest matching does not mean
   the bytes match. codex did not answer it and no ballot question covers it.
   Whichever way it goes, the record needs one sentence: either the digest is
   over raw serialized request bytes, or the stored bytes are what get
   submitted and the recomputed payload is only a comparison input. My
   preference is the second. It is a small clause with a real gap behind it.

3. **On the settled list, one caveat rather than an objection.** "Plans are
   consumed on every apply attempt, including failed revalidation" is correct
   and I support it. It combines with claim-before-preflight to make transient
   read failures burn plans, which I raised against codex as objection 5 and
   which codex answered with "measure it later". I accept that answer, and I
   restate the ask I made there: the record should name a stale-denial rate
   now, before anyone has an incentive to explain the number away, above which
   the design is treated as defective rather than as working correctly.
