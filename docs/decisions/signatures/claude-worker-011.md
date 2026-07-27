# Signature on decision record 011, claude-worker

- **Record:** `docs/decisions/011-deploy-path-repair.md`
- **Read for this signature:** the whole record, `docs/proposals/4/SPEC.md`,
  `docs/proposals/4/WORKPLAN.md`, `docs/proposals/4/TLDR.md`, my ballot
  `docs/proposals/4/claude-worker-ballot.md`, my critique
  `docs/proposals/4/claude-worker-critique.md`, my proposal
  `docs/proposals/4/claude-worker-proposal.md`, and both peers' ballots for the
  tally check
- **Branch:** `claude/r4-deploy-permissions` at `a5341730`

## 1. Is my ballot tallied correctly?

**Confirmed, both questions, including the declared interest.**

| Question | My ballot | Record's table and prose | Match |
| --- | --- | --- | --- |
| A, split `deploy` into `build` and `deploy` | for, interest declared as "I proposed the split, and I am the one who dropped the `needs.build.outputs.digest` mechanism that both peers attacked, so read this vote as a party's" | for, interest "proposed the split, dropped the attacked mechanism", 4-0 | yes |
| B, rename this round | for, in the standalone-commit form, "Not a party to this one", and explicitly "Not conditional on A" | for, "standalone-commit form", interest "not a party", 3-1 | yes |

Two prose attributions on Question A are also mine and are correct: that
round-branch publication should be a numbered decision the principal can veto,
and that the fallback is a single `deploy` job. The record adopts the
claude/codex fallback over agy-worker's variant and states agy-worker's variant
alongside it rather than dropping it, which is the right handling.

The record does not carry my "not conditional on A" statement on Question B.
That is not a defect: the vote is recorded as unconditional, which is what the
statement means, and codex-worker's dissent is the only ballot on that question
whose conditionality mattered.

## 2. Dissent preservation

**Confirmed. I am not codex-worker, so the check I can perform is the one asked
of a non-author, and I performed the verbatim check anyway.**

I diffed the record's block quote at lines 197 to 201 against
`docs/proposals/4/codex-worker-ballot.md` lines 14 to 18. It is word for word,
including the bolded lead, the "regardless of Question A" qualifier, and the
closing "I previously argued to defer the rename." Nothing is truncated, no
elision is unmarked, and nothing is softened.

I also confirm the record does not misstate any position I took in phase 2. My
positions in the record's critique section are: that codex-worker's local
`/healthz` 200 gate is unsatisfiable, that the repo default of `read` kills my
own workflow-level argument, that my hearthgate citation was misleading, that
agy-worker's private-package prediction is refuted by measurement, and that
agy-worker's deploy runbook dies at an ssh to `deploy@` before the pull it
predicts. All five are stated as I stated them.

## 3. Characterization: concessions and critiques

**Confirmed. No concession is attributed to me that I did not make, and none of
my critiques is softened.**

Checked one by one against my critique's section 4:

- **Job-level `permissions:` and the withdrawn conclusion.** Mine. The record's
  framing that the question "was settled by a value, not a principle" is exactly
  the frame I used: I conditioned my phase-1 argument on a setting I had not
  read, read it, and the argument died.
- **The withdrawn evidence.** The record says I withdrew my supporting evidence
  as well as my conclusion, and that hearthgate's actual practice is
  scope-per-workload and therefore evidence for codex-worker's placement. That is
  my wording and my conclusion, including the reason I wanted it recorded, which
  was that a reviewer trusting my original citation would have been led wrong.
  The record carries that reason. I asked for it and I am satisfied it landed.
- **The dropped `needs.build.outputs.digest` mechanism.** Recorded accurately as
  a concession that changed Question A's terms, and the record correctly explains
  why Question A was re-balloted rather than counted from the critiques.
- **The constitution point on agy-worker's estimate.** The record resolves it as
  loose phrasing and preserves the substantive half. That is the resolution I
  invited: I wrote that I accept it is most likely loose phrasing rather than
  intent. I do not contest the ruling.
- **agy-worker's headline risk refuted by measurement.** The record credits
  codex-worker and me with landing the missing-secrets point independently and
  credits the anonymous GHCR token probe as the refutation. Accurate. It also
  correctly notes codex-worker reached the visibility conclusion by reasoning
  before I had the measurement, which is a concession I made and which the record
  did not have to carry.

Nothing is attributed to me as conceded that I contested, and nothing I
contested is recorded as settled without my objection alongside it. The
orchestrator's independent re-verification list matches what I measured in my
critique's section 0 on every item I measured: the `read` default, the secret
and variable inventories, `404 Branch not protected`, the 503 path and the
`SESSION_SECRET` raise, the absent concrete `AuditRepository`, the absent
compose file, and the two GHCR token responses. I have no correction to offer to
any of it.

## 4. The synthesis, the labor split, and the five decisions

**Accepted.** I accept 011 as the team's decision, including `SPEC.md`,
`WORKPLAN.md`, the five decisions in `SPEC.md` section 4, and the division of
labor.

On the labor split specifically, since the dispatch invites a dispute: I do not
dispute it. codex-worker owning Slice A is the right call for the reason the
workplan gives, and I said in phase 1 that the file should have one owner. One
small clarification for a later reader, not an objection: my proposal also said
"I am happy to be the non-author reviewer on Slice A," so my declining the
ownership was not a declining of all involvement. `WORKPLAN.md` addresses that
directly, that two non-authors is one more than the gate needs, and I accept it.
The record's "gets no part of Slice A" is true as decided; it just is not a
position I volunteered in full.

Three defects follow. None of them is in the decision, all three are in the
documents the decision points at, and none blocks my signature.

**F1. `WORKPLAN.md` step 3 instructs a doer to do something the constitution
forbids, and steps 3, 5, and 6 are ordered so the proof cannot happen when the
plan says it does.**

Step 3 reads "Write and push Slice A to `round/4-deploy-permissions`.
codex-worker." Doers never push, and they do not commit to the round branch.
Slice A belongs on `codex/r4-deploy-permissions`, and the orchestrator merges it
into the round branch after sign-off.

That is not only a wording problem, it inverts the plan. The workflow triggers on
`push: branches: [main, "round/*"]` only. A commit sitting on `codex/*` triggers
nothing. So the round-branch build that step 3 claims proves D1 cannot run until
the orchestrator has integrated the branch, which is step 6. Step 5, reading the
package back, depends on that same push having happened, and it is also placed
before step 6.

Fix: step 3 becomes "commit Slice A to `codex/r4-deploy-permissions`", the
sign-off gate moves up to sit immediately after the static check, and the
round-branch run plus the package readback follow integration. The
capability-based assignments do not change and neither does anything in the
decision. Only the order and the actor of the push change.

**F2. `TLDR.md` carries four of the five decisions. Decision 5 is missing.**

`SPEC.md` section 4 enumerates five decisions for the principal. The TLDR's
"What we need from you" lists the scope split, the deploy-key identity and
host/URL configuration, the forced-command question, and round-branch
publication. Decision 5, where `SESSION_SECRET` comes from, appears nowhere in
the TLDR.

The TLDR is the document the principal actually reads on the issue, so a
decision that reaches `SPEC.md` and not the TLDR has not reached the principal.
I have a declared interest here and I will state it plainly: this is my own
finding from phase 2 repeating one step further along. My critique's concession
list says I buried the `SESSION_SECRET` design call inside a scope discussion
instead of raising it as a decision. The synthesis correctly promoted it to a
numbered decision, and then the summary dropped it again.

Fix: one bullet in the TLDR stating the two options and that the team leans B,
flagged as Slice B so the principal knows it is not blocking Slice A. If the
deliberate intent was to hold it back until Slice B is filed, then `SPEC.md`
section 4 should say so, because as written the two documents disagree about
what is being asked.

**F3, minor. `WORKPLAN.md` step 7's third failure signal and its closing note
are both correct and they sit apart from each other.**

The step-7 bullet describes the health poll exhausting 12 tries as "expected if
Slice B has not landed", and the paragraph after it states plainly that step 7
is expected to end red. That is the single most important operational fact in
the round and the reader meets it twice, in a bullet list of failure signals and
then in prose. I would put the "this run is expected to end red, and here is
exactly where" statement first, before the failure-signal list, because a reader
skimming the list will read "expected" as a hedge rather than as a prediction.
Presentation only, and it is the item the workplan itself calls the most
expensive possible misdiagnosis, which is why I am naming it at all.

## Verdict

I accept 011 as the team's decision, with no standing dissent on any question.
My Question A vote is a party's and is recorded as such, my Question B vote is
recorded in the form I cast it, and codex-worker's losing position is preserved
word for word. The orchestrator's independent verification agrees with every
measurement I took, and I found nothing in it to correct.

F1 is worth fixing before Slice A starts, because it tells the owning doer to
push and it puts the proof step before the integration that makes the proof
possible. F2 is worth fixing before the issue comment goes out, because a
decision the principal never sees is not a decision. F3 is presentation. None of
the three changes what gets built or who builds it.

Signed-off-by: claude-worker <claude@team.local> 2026-07-27T01:56:40Z
