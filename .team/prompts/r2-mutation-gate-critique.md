# Phase 2: adversarial critique

Phase 1 is closed. All three proposals are committed. You now read the other
two and attack them.

## The three proposals

Read all three from your own worktree with `git show`. All three branches are
in the same object store, so this works without entering anyone's worktree.
**Do not check out, enter, or modify another resident's worktree.**

| Worker | Commit | Path |
| --- | --- | --- |
| claude-worker | `ce6e6c05c166edf29bfc2f31a0041a370df0fc7e` | `docs/proposals/claude-worker-r2-mutation-gate-proposal.md` |
| codex-worker | `63567bf885c6a6fda1365ba3122c22c3fdcc8b45` | `docs/proposals/codex-worker-r2-mutation-gate-proposal.md` |
| agy-worker | `a08f6ae0ad64f4d3e2d1a05fab7fefc00e7d55e4` | `docs/proposals/agy-worker-r2-mutation-gate-proposal.md` |

For example:

    git show ce6e6c05c166edf29bfc2f31a0041a370df0fc7e:docs/proposals/claude-worker-r2-mutation-gate-proposal.md

Re-read your own too. You are allowed to change your mind, and saying so is
worth more than defending a position you no longer hold.

## Adversarial means adversarial

Actually try to find what is wrong with the other two proposals. Not "here is
an alternative worth considering". Not "this is solid, though one might also".
A critique round in which everyone says the proposals look good is a **failed
round**, not a converged one, and I will send it back.

What I am looking for, in rough order of value:

- **A claim that is false.** Especially a factual claim about the VCF Ops API
  that recon can settle. Read-only GETs against DEVEL are allowed and
  encouraged. Nothing against prod, no mutations anywhere, ever.
- **A security hole.** A path where a mutation reaches a live appliance without
  passing the gate, where a read-only target gets mutated, where the prod hard
  block is routed around, or where a stale plan still executes. That is the
  whole point of this round.
- **A gap the proposal does not know it has.** The thing it assumed rather than
  checked.
- **An internal contradiction**, where a proposal's own reasoning defeats
  another part of it. Round 1 turned on exactly this.
- **A cost the proposal did not price.** Latency, upstream load, tool-surface
  budget for a tool-calling-only client, operator round trips.

Attack the strongest version of each proposal, not a weak reading of it. If you
have to misread it to defeat it, you have not defeated it.

**Concede what is right.** If a peer found something you got wrong, say so
plainly and in your own words. Round 1's most useful single artifact was a full
concession. A concession is not a loss; it is the protocol working. Do not
manufacture a disagreement to look rigorous, and do not soften a real one to
look agreeable.

## Points where I already know you disagree

I am naming these because they are where the synthesis will actually turn, and
I want them argued rather than left implicit. This list is not exhaustive and
is not a ranking. Do not confine your critique to it.

1. **On a failed revalidation, does the denial carry a freshly issued plan for
   the same intent?** claude-worker says yes, and calls it a round-trip saving
   that changes no gate property because the new plan goes through the
   identical checks. codex-worker and agy-worker independently say no, on the
   grounds that confirmation must bind to the exact summary and payload the
   operator actually saw. This is the sharpest three-way split in the round.
   Argue it on operator safety, not on convenience.

2. **What is the alert unit?** codex-worker and agy-worker both scoped an
   `alert_ack` operation. claude-worker's recon reports that the endpoint is
   `POST /api/alerts?action=<verb>` and also accepts suspend, release, and
   assignownership, and argues that naming the operation "ack" names the wrong
   unit. If that measurement holds, it bears directly on the other two
   proposals. Check the measurement rather than assuming it.

3. **Bulk and partial success.** claude-worker reports the alert endpoint takes
   a list of alert IDs, so N alerts can come back partly applied, and proposes
   capping MVP at one alert per plan while calling the cap a deferral rather
   than a solution. codex-worker wants per-alert outcomes in the plan and audit
   model and no automatic whole-batch retry. Whether a cap is an acceptable MVP
   answer is a real question.

4. **Is revalidating an action by re-running populate safe?** claude-worker
   flags that populate is a POST and that it has not proven it idempotent or
   side-effect-free. agy-worker proposes re-running validate at apply and names
   the same worry about validate. If either call has side effects, both
   proposals need a different revalidation source. This is checkable against
   the OpenAPI without mutating anything.

5. **Tool surface and schema.** All three keep the surface at six tools via a
   discriminated union. codex-worker itself flags that a tool-calling-only
   client such as VCF Private AI Services may render or validate union branches
   poorly, and offers a typed-planner hybrid as a fallback. If the union is a
   real client problem, it defeats part of all three proposals at once, so
   somebody should press on it.

## Constraints

Unchanged from phase 1, and still binding:

- No production code. You are critiquing an amendment to a decision record.
- Fork 1 stays closed. No dynamic tool generation.
- Read-only recon against DEVEL only. Nothing against prod. No mutation of any
  kind against any live appliance, including acknowledging a real alert to see
  what the response looks like. If a question can only be answered by mutating,
  the answer is that it stays an open risk in the record.
- Scott's two rulings (fine-grained default-deny authorization, and grantable
  scopes derived from implemented capabilities) are settled and are not
  re-litigated. Critiquing whether a proposal *correctly applies* them is fair
  and welcome.
- No new dependencies. No credentials or lab-specific configuration in
  anything you commit.
- No em-dashes anywhere, including the commit message. Hard repo rule.
- `Co-authored-by:` trailer naming you. Do not push. Do not open a PR.

## Required output format

**1. Critique of each of the other two proposals, separately.** For each, lead
with the single strongest objection you have, and number the rest. For every
objection, say what it would take to change your mind. An objection nobody
could ever answer is a preference wearing a costume.

**2. Concessions.** What the others got right that you got wrong or missed.
Explicit, in your own words, naming which worker and which point.

**3. Where you have changed your position**, if anywhere, and to what.

**4. Any new recon you performed**, with the actual numbers and the endpoint
you read. Say plainly if you performed none.

## Ship it as a commit

Write your critique to `docs/proposals/<your-prefix>-worker-r2-mutation-gate-critique.md`
on your existing `<your-prefix>/r2-mutation-gate` branch and commit it. Report
the full 40-character SHA and the branch.

Reading copies of the peer proposals into an untracked `scratch/` directory in
your worktree is fine and does not merge. Do not commit them.

Use the real output of `date -u` for any timestamp. Do not guess the current
time. Your turn is over when the critique is committed and the SHA reported.
