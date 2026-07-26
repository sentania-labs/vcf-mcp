# Signature on decision record 009, claude-worker

- **Record:** `docs/decisions/009-phase1-build-synthesis.md`, including
  Amendment 1
- **Read for this signature:** the whole record, `docs/proposals/2/SPEC.md`,
  `docs/proposals/2/WORKPLAN.md`, `docs/proposals/2/TLDR.md`, my ballot
  `docs/proposals/2/ballots/claude-worker-r3-p1-ballot.md`, my proposal
  `bfc23827` and my critique `48b68d07`
- **Branch:** `claude/r3-signoffs` at `1d44971`

## 1. Is my ballot tallied correctly?

**Confirmed, all seven questions and both sub-questions.**

| Question | My ballot | Record's table and prose | Match |
| --- | --- | --- | --- |
| 1 | 1B, with a binding rider that admin security writes fail closed, otherwise 1A | **No (1B)**, 4-0, rider adopted as part of the decision, and the record states that without the rider my vote is 1A | yes |
| 2 | 2C, SQLite, no rotation | **SQLite, no rotation (2C)**, 3-1 | yes |
| 3 | 3B, four corrections accepted, conditional on funding the live tier | **3B, four corrections**, 3-1, live tier budgeted as a named workplan item | yes |
| 4 | 4B | **4B, explicit per-request counter**, 4-0 | yes |
| 5 | 5B | **5B, capability + frozen allowlist**, 4-0 | yes |
| 5-sub | yes, both ship | **Yes**, 4-0 | yes |
| 6 | 6B, with the open registration mapping and skills out of delivery | **6B, spine with two corrections**, 4-0 | yes |
| 6-sub, three main slices | codex spine, claude read plane, agy delivery | same | yes |
| 6-sub, skills | codex-worker | recorded as my vote, 2-2, critic decided for agy-worker | yes |
| 7 | 7C-with-payload | **7C-with-payload**, 4-0 | yes |
| 7-sub | escalate no, with two conditions | **No, with conditions**, 4-0, both conditions adopted | yes |

The prose attributions to me are also right: I reversed my own 1A (decision 1),
I withdrew my own 2A argument (decision 2), I noted the live tier appeared in no
slice's file list (decision 3), I named myself the party at fault on both retry
holes (decision 4), registration-time binding is retained from me and codex's
tripwire correction is adopted over my version (decision 5), and I withdrew 6C
on codex's attack 7 (decision 6). Decision 1's rider is recorded with my
condition attached rather than as an unconditional 4-0, which is the thing I
most wanted checked, and it is correct.

## 2. Are my dissents and objections verbatim, and not softened?

**Confirmed on wording. Three unmarked truncations noted, one of which I want
fixed.** No quoted sentence has been altered, reordered, or softened. Every
character inside every quotation mark matches my ballot. What is missing is at
the edges:

1. **Reports objection, front truncation, and this is the one I want fixed.**
   The record's quote begins "Record 007 makes report run a mutation". My ballot
   bullet begins "**The Phase 1 reports family should be cut to nothing, or to
   definitions only.** Not on the ballot and it should have been." The dropped
   sentence is my only procedural objection in the whole round, that reports
   scope should have been balloted rather than carried as an objection, and it
   appears nowhere else in 009. The substantive remedy survived and was adopted,
   so this does not block my signature, but I ask that "Not on the ballot and it
   should have been." be restored to the quote in a later edit.
2. **Reports objection, tail truncation, unmarked.** The quote stops after "run
   path" and omits my stated remedy: "I would ship report definitions listing
   only, or drop the family from Phase 1 entirely and let it land whole in Phase
   2 alongside run." Not softening, since Amendment 1 adopts the first half of
   exactly that remedy and the TLDR carried it to the principal. A trailing
   `[...]` would be more honest than a clean stop.
3. **TLS objection, tail truncation, unmarked.** The quote ends "by never being
   asked." My ballot reads "by never being asked, and asking that the workplan
   carry it as an explicit question to Scott at Gate 1." The comma became a
   period and the operative ask was dropped. The mid-quote elision is marked
   with `[...]` and the tail one is not. Again not softening in effect: the ask
   is honored by the risk register line and by Gate 1 packet item 6. Same
   request, mark it.

The 6-sub losing objection is quoted exactly and in full from my ballot's final
bullet, and the critic's requirement that it be preserved is met.

## 3. Are my concessions overstated?

**Confirmed, none is overstated.** I checked each one against the ballot text it
came from:

- Decision 2, "Anyone who can delete rows can also rewrite lines." Mine,
  verbatim, and it is the concession I intended to make.
- Decision 3, my generator "would have silently destroyed the contract it was
  built to preserve." Mine, verbatim, and correctly framed as a correctness fix
  rather than a security fix, which is how I framed it.
- Decision 4, my ballot "names itself the party at fault on both." Accurate. I
  wrote "I am the party at fault on both."
- Decision 5-sub, my earlier counter "was not a counter", and the quoted
  "is not a tested branch, it is an untested branch with a comment on it."
  Both accurate.
- Decision 7, "claude-worker abandoned the plain-success position from its own
  critique 1.4." Accurate and correctly narrow. I abandoned the type, not the
  argument against withholding, and the record adopts that argument separately
  in its 7A reasoning. My ballot said "partly abandoning it" and the record's
  sentence names precisely the part.

Nothing is attributed to me as conceded that I contested, and nothing I
contested is recorded as settled without my objection alongside it.

## 4. Is any measurement misstated?

**Confirmed for every figure I measured. No correction needed.**

- **137,808 bytes for one resource at `maxSamples=1`.** Mine, from proposal
  `bfc23827`. The record states it correctly, including the `maxSamples=1`
  qualifier, which is the qualifier that makes it alarming rather than merely
  large. SPEC section 2 and section 5 carry it identically.
- **The `OpsToken` header result.** Mine. Both `OpsToken` and
  `vRealizeOpsToken` return 200, an arbitrary scheme returns 401, so the
  appliance holds a case-insensitive allowlist of scheme names, and record 006's
  selection of `OpsToken` stands with the alias as a comment. That is exactly
  what I measured and exactly what the record says.
- **142 action definitions.** Not cited in 009 at all. It is my measurement from
  rounds 1 and 2, recorded in records 001 and 007, and both state it correctly
  (142 definitions, all `type: UPDATE`, 66 distinct display names, no parameter
  metadata). Nothing to correct.
- **517 objects, 21 adapter kinds, 169 VMWARE, 52 CONTAINER.** Not mine. My
  ballot states I took no recon this phase, and my own earlier measurement was
  the 4-object figure that the record correctly describes as superseded. I
  cannot confirm or deny the 517 numbers from my own work and I do not
  second-guess them; they are consistent with the permissions fix the record
  describes.
- The consequences section's handling of record 001's "508 resources /
  1,097,361 bytes / 92 percent" caveat matches what I wrote in my own proposal.

## 5. Is Amendment 1's reading of the principal's approval honest?

**Confirmed for all three. A bare `approved` carries each of them, for the
purpose the amendment actually claims. Two qualifications, neither blocking.**

The amendment's claim is narrow and that is what makes it defensible: it
authorizes implementation on the answer the spec already states, and it keeps
each question open rather than closing it. If it had read `approved` as closing
any of the three, I would be denying this item.

1. **Reports definitions-only. Carried.** The TLDR asked the question in plain
   words and stated the team's answer ("I'd ship report definitions listing
   only"), SPEC section 6 states it as the shipping decision, and the TLDR says
   in terms that `approved` starts the build. Approving a document that answers
   its own question approves the answer. I declare an interest: this is my own
   objection being adopted, so I am the wrong party to be enthusiastic about it,
   and I have tried to check it as if it had gone the other way.
   **Qualification:** the amendment says each of the three "stays open as a Gate
   1 packet item where the spec said it would". For reports that clause is doing
   real work, because reports is **not** in SPEC section 15's packet list. Only
   the audit reading and the TLS question are. So of the three, this is the one
   with no scheduled re-ask, and if the principal disagrees the discovery point
   is after the family is built. SPEC section 6 already prices the reversal at
   roughly one extra dispatch-day in my slice, so the exposure is bounded and
   named. I recommend, without conditioning my signature on it, that the reports
   scope be added as a seventh Gate 1 packet item so the reduction is confirmed
   in the same place the other two are.
2. **TLS verification off for the first DEVEL registration, CA bundle preferred
   and still the principal's call. Carried, and this is the strongest of the
   three.** It is the reading I asked for. My objection was never that
   `verify_ssl=false` is wrong for a first registration, it was that it must not
   become permanent by never being asked. The amendment ships the honest
   labelling, keeps the CA bundle as the preferred answer, keeps it as the
   principal's call, and pins it as Gate 1 packet item 6 precisely so it gets
   asked again. Not budgeting fingerprint pinning is correct on codex-worker's
   handshake argument, which I accept.
3. **The audit invariant reading. Carried, but it is the weakest of the three
   and I want the cost of a late overrule stated.** The TLDR bullet did not
   merely state the reading, it asked for an affirmative word ("it's your
   invariant and you should get to say so"). Reading silence as assent to a
   request for an explicit yes is the thinnest of the three inferences. It still
   holds, for one reason: the amendment does not treat the reading as ratified.
   It states it in the team's own words, says the principal may overrule it at
   Gate 1, and keeps it as a named packet item. That is exactly condition 1 of
   my own 7-sub vote, which was that the interpretation be written down so it is
   the principal's to overrule rather than decided by omission. Decided by
   omission is what the amendment avoids; it decides it in writing, provisionally,
   and hands the principal the pen.
   **Qualification, and this is the useful half of my answer:** an overrule at
   Gate 1 is not free. Decision 7's own reasoning is that a terminal state on
   the dispatcher's public contract is expensive to change later, touching the
   dispatcher, every tool's response contract, the admin UI, the reconciliation
   surface, and any client. If the principal rejects the reading at Gate 1, that
   is the change we would then be making, at the moment the record says is the
   worst time to make it. The amendment should say so, so that the principal
   knows the item is cheaper answered early than at Gate 1. I would ask the
   orchestrator to surface this one item ahead of Gate 1 rather than in the
   packet, and I am content for that to be a note rather than a condition.

I found nothing dishonest in the amendment. It does not claim the principal
answered a question he did not answer, it does not convert any of the three into
a closed decision, and it does not use the approval to reach anything beyond the
pinned content at `5940ea8`.

## 6. Are my slice's acceptance criteria buildable as written?

**Confirmed for six of eight. Two are underspecified, and I am naming both now
rather than mid-build. Neither blocks my signature; one needs a line in
`contracts.py` at step 1, which is cheap only if it is asked for before step 1
lands.**

Buildable as written, no ambiguity:

- Exactly one token acquisition across N concurrent 401s. Tier 2, MockTransport,
  countable.
- No re-auth on 403. Tier 2, assert acquire count unchanged.
- Per-request retry counter bounds retry at exactly one under mid-session
  credential revocation. Tier 2, a transport that 401s unconditionally, assert
  the typed terminal error and the request count.
- Every adapter declares its `(method, path template, permitted query parameter
  names)` triple and its projection version. Mechanical, and the registry
  refusal is codex's side of the seam.
- The fixture generator preserves reference equality, rejects unknown schema
  paths, and emits generator version, source API version, and generation date,
  with a proof test that no raw capture token reaches output.
- Contract tests assert shape and monotonic properties, never exact object
  counts.

**Underspecified 1, and it is a cross-slice seam, not a detail I can settle
alone: "Target edit marks the old client closed, and its drain-or-cancel
semantics are documented and tested."** The semantics are mine to define and
document, and I accept that. What is not defined anywhere is *who tells me*. The
client registry is in my slice, the target repository is codex-worker's, and the
admin write path that performs the edit is agy-worker's. The workplan's step 1
enumerates `ToolContext`, `ToolSpec`, `Capability`, `TargetRecord`,
`TargetPosture`, the repository protocols, and the registration mapping. It does
not enumerate a target-change notification or client-invalidation protocol. So
the one mechanism that three slices must agree on to satisfy this criterion is
absent from the only planned serialization point, which makes it exactly the
recurring three-way edit that decision 6's open-mapping correction exists to
prevent. **Ask: `contracts.py` carries a target-configuration-generation and
invalidation protocol at step 1.** I will raise this to codex-worker at step 1
rather than discovering it in week two, and I am recording it here so that the
raise is on the record rather than in a side channel.

**Underspecified 2: "Metrics caps refuse rather than truncate, with the cap
named in the refusal."** The refusal behavior and the message are unambiguous.
The cap itself is not: SPEC section 5 defines it as a bound on the product of
resource count, stat-key count, and sample count, and no numeric value appears
in the spec or the workplan. Compare codex-worker's slice, which was explicitly
required to specify free-space reservation "numerically, not as 'a conservative
threshold'". Mine has the same shape of gap and no such requirement. I do not
think this needs a ruling: the number is a per-family declaration field, which
is the concrete case the open registration mapping was adopted for, and I will
derive it from the measured 137,808 bytes for one resource at `maxSamples=1`,
state the derivation in the adapter, and put it in the Gate 1 packet as a number
somebody can argue with. Recording it so that "claude picked a number" is a
declared act rather than an inherited constant.

One scheduling note, not a criterion defect. My named work is 4 to 6 dispatch-
days for the read plane, plus 1 to 2 for the live tier, plus roughly 1 for the
suite-api auth walkthrough seed content, so 6 to 9 total against a slice line
that reads 4 to 6. The workplan does budget the live tier and the content
separately and honestly, so the total is stated, just not in one place.

## Verdict

I accept 009, including Amendment 1, as the team's decision. Two of the seven
questions went against my proposal by my own vote and one went against my vote
by the critic's; all three are recorded accurately and my losing position is
preserved verbatim. The three requests above (restore the dropped procedural
sentence in the reports quote, mark the two tail truncations, add reports scope
to the Gate 1 packet) are corrections to the record's presentation and to the
packet, not to the decision, and none of them changes what gets built.

Signed-off-by: claude-worker <claude@team.local> 2026-07-24T22:00:03Z
