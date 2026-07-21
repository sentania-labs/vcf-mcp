# Phase 3 close: peer-review one branch, and sign record 007

You are claude-worker. Two artifacts, both committed on your **new** branch
`claude/r2-signoffs`, which is already checked out in your worktree and branched
from `round/1-architecture` at `6b7bdcf`.

Your `claude/r2-mutation-gate` branch is **frozen** at its ballot head and must not
receive further commits. That is deliberate: your peer's sign-off marker names
that exact SHA, and a marker stops covering a branch the moment the branch moves.

## Artifact 1: peer review of `codex/r2-mutation-gate` at `74a675b3ccdf0530aef4950f5e5f9beb00c3f8ef`

You did not author it, so you are an eligible reviewer.

Read it with `git diff` and `git show` from your own worktree. **Do not enter,
check out, or modify codex-worker's worktree.**

Review the range `a14b80f..74a675b3ccdf0530aef4950f5e5f9beb00c3f8ef`, which is codex-worker's proposal, critique, and
ballot. What to check:

- No credentials, tokens, or lab-specific configuration.
- No em-dashes.
- `Co-authored-by:` trailer on every commit.
- **Nothing in it violates the constitution**, in particular that no mutation of
  any kind was issued against any live appliance and nothing at all was issued
  against prod. Recon claims should be read-only GETs. If you find evidence of a
  mutation, that is a constitution violation: say so, withhold the sign-off, and
  state it plainly.
- Factual claims about the VCF Ops API are checkable against
  `vcf-content-factory/reference/docs/operations-api-9.1.json` and against
  read-only DEVEL. You already disputed some of them in phase 2. If a claim you
  disputed is still stated as fact in the frozen artifact, that is expected: the
  artifacts are a record of what each worker believed at the time, not a
  corrected document. Do not withhold a sign-off over a claim the protocol has
  already adjudicated. Withhold only for a constitution violation, a leaked
  secret, or a defect in the artifact as an artifact.

Write the marker per `.team/signoffs/README.md`, named and formatted exactly as
that README requires, with `reviewed_by: claude-worker` and
`authored_by: codex-worker`. Read the README; it is the authority, and this round
already had two markers bounced by an external reviewer for missing fields.
Use the real output of `date -u` for `timestamp`.

## Artifact 2: your signature on decision record 007

Read `docs/decisions/007-mutation-gate-generalization.md` on your branch. Also
read the amendments to records 001, 003, 004, and 006 in commit `6b7bdcf`,
which fold in Scott's five resolutions.

Write `.team/signoffs/claude-worker-r2-records.md` stating whether you accept
record 007 as the team's decision. Follow the shape of the round-1 signature
artifacts (`.team/signoffs/claude-worker-round1-records.md`) for front matter.

**What your signature is actually attesting.** Not that you agree with every
ruling. That you have read the record and that it represents the round
faithfully. Specifically, confirm or deny each of these:

1. The ballot tally for your votes is recorded correctly.
2. You have no recorded dissent on record 007. Several of your ballot objections were adopted into the decision (the ownership verbs being not implementable rather than deferred, the submitted-bytes ruling, and the stale-denial-rate ruling). Confirm they are represented accurately, and confirm that the withdrawal of your fresh-plan proposal is recorded in codex-worker's framing as you asked rather than as your retraction.
3. Any concession attributed to you is quoted accurately and was not softened,
   truncated, or reworded.
4. No claim you measured is misstated.

**If the record misstates something, say so and do not sign it.** A withheld
signature with a stated reason is a valid outcome and is more useful to me than
a signature I have to discount. I would rather amend the record than carry an
inaccurate one.

Two rulings in record 007 were made by me rather than balloted, and both are
flagged as orchestrator-authored in the record itself: the **submitted-bytes**
ruling and the **stale-denial-rate** ruling. If you think either is wrong, say
so in your signature artifact. Disagreeing with them does not prevent you from
signing, since they are flagged as mine, but I want the disagreement recorded
rather than absorbed.

## Constraints

No production code. No new dependencies. No credentials or lab-specific
configuration. Read-only DEVEL recon only, nothing against prod, no mutations
anywhere ever. No em-dashes anywhere including commit messages.
`Co-authored-by:` trailer naming you. Do not push. Do not open a PR.

## Done means

Both artifacts committed on `claude/r2-signoffs`. Report the full 40-character
SHA, and say plainly for each artifact whether you signed or withheld and why.
