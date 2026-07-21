# Phase 1: propose, blind

You are one of three workers proposing an approach to the assignment below,
independently, in parallel, right now. You will not see the other two
proposals until phase 1 closes, and they will not see yours.

**Branch:** `<your-prefix>/r2-mutation-gate`, already checked out in your
worktree, branched from `round/1-architecture` at `a14b80f`.

## Assignment

Record `docs/decisions/001-action-tool-surface.md` is accepted and merged into
the round branch. PR #1's external Codex review found two defects in it. Both
are real, I have accepted both, and neither is up for debate. What *is* up for
debate is how record 001 should be amended to fix them, and that is what you
are proposing.

Read record 001 first. It is the thing you are amending, and its reasoning is
binding context, not a suggestion.

### Defect 1, verbatim from the external review

> **Route alert acknowledgements and report runs through plans**
>
> For the required alert-acknowledgement and report-run operations in
> `docs/SPEC.md`, this plan shape is action-definition-specific and requires an
> action ID and definition fingerprint, even though those operations use
> separate API families. The source proposal explicitly said both would use the
> shared plan service, but the accepted record omits that mapping and exposes
> only `plan_action` and `apply_action`; implementers must therefore either omit
> these MVP operations or add an unrecorded mutation path that bypasses the
> mandatory plan gate. Define a generalized operation type and payload
> fingerprint, or specify dedicated plan/apply paths for both families.

`docs/SPEC.md` section 4.1 corroborates this: alerts are specified as
"alerts, symptoms, acknowledge (**acknowledge counts as an action for gating
purposes**)" and reports as "list/**run**/download". Both are mutations. Record
001's plan record is built around an action ID and a definition fingerprint
drawn from `GET /api/actiondefinitions`, which neither family has.

### Defect 2, verbatim from the external review

> **Revalidate the action against VCF Ops before applying**
>
> When resource state, parameter applicability, or populated defaults change
> between planning and applying, every check listed here can still pass: the
> parameter digest only proves the stored parameters were not modified, and the
> catalog record is explicitly documented as containing no parameter metadata.
> The accepted critique in `docs/proposals/codex-worker-round1-critique.md`
> required repopulating or validating against VCF Ops before mutation, but that
> freshness check was dropped from the synthesized decision, allowing a stale
> plan to execute a destructive action.

### The question you are answering

**How should record 001's mutation gate be amended so that every mutation this
project ships is covered by plan-then-apply, and so that a stale plan cannot
execute?**

The external review named two candidate directions for the first defect and did
not choose between them:

- a **generalized operation type** with a payload fingerprint that covers all
  mutation families under one plan/apply path, or
- **dedicated plan/apply paths per API family**.

Do not treat those two as the only options, and do not treat them as
pre-ranked. If a third shape is better, propose it and say why.

I am giving you both defects as one assignment on purpose, because I think they
are coupled: where pre-apply revalidation hooks in depends on how the gate
generalizes, and "revalidate" cannot mean the same operation for an
actiondefinition, an alert acknowledgement, and a report run. If you think they
are in fact separable, say so and argue it. That is a legitimate finding.

Points worth resolving in your proposal, though this list is not exhaustive and
is not a spec:

- What replaces or generalizes the definition fingerprint for a family that has
  no action definition.
- What "revalidate immediately before applying" concretely means per family,
  what it costs in latency and extra API calls, and what happens when the
  revalidation call itself fails or times out. Record 001 already establishes
  `outcome_unknown` as a terminal state; say how yours interacts with it.
- Whether the six-tool action family grows, gains siblings, or stays fixed
  while the plan record generalizes underneath it. Tool-surface cost matters:
  record 001's whole reasoning was about what a tool-calling-only client such as
  VCF Private AI Services can carry.
- How this interacts with the read-only default, the per-target action
  enablement toggle, and the prod hard block. An alert acknowledgement against
  a read-only target must refuse server-side.
- Whether a revalidation that comes back *changed* fails the apply, or returns
  a new plan for re-confirmation, and what that means for an operator's
  workflow.

### Scott's rulings, settled, do not re-litigate

Handed down today, after record 001 was written. Treat as binding:

1. **Action authorization is fine-grained and default-deny.** Each API key
   carries a specific allow-list of action-classes, intersected with a global
   policy. A newly minted key can do nothing until scopes are explicitly
   granted.
2. **Grantable scopes derive from implemented capabilities**, read or write. A
   scope is assignable only if the server actually implements the matching
   capability. No minting a `read_logs` scope when no `read_logs` tool exists.
   Action scopes are not grantable until the action machinery ships and clears
   the Phase 2 gate.

Ruling 2 bears directly on your proposal: if you introduce new mutation
capabilities for alerts or reports, say what their scopes are called and how
those scopes become grantable only once implemented.

## Constraints

Beyond the constitution:

- **This round still merges no production code.** You are amending a decision
  record. Do not write `src/vcf_ops_mcp/`.
- **Do not reopen fork 1.** No dynamic tool generation. That is settled, the
  reasoning is measured, and it is not what this assignment is about.
- **Read-only recon against DEVEL only**
  (`vcf-lab-operations-devel.int.sentania.net`), nothing against prod, no
  mutations against any live appliance ever. If you want to verify the shape of
  the alerts or reports API, reading it from devel is allowed and encouraged.
  Acknowledging an actual alert is not, under any circumstances.
- No new dependencies.
- No credentials, tokens, or lab-specific configuration in anything you commit.
- No em-dashes anywhere, including commit messages. Hard repo rule.
- `Co-authored-by:` trailer naming you on every commit.
- Do not push. Do not open a PR. Do not touch another resident's worktree or
  branch.

**Protected paths this is expected to touch:** none directly. Record 001
governs `src/vcf_ops_mcp/` prospectively, so your amendment constrains a
protected path without editing one.

## Blind means blind

Do not read the other residents' proposals, branches, worktrees, or scratch
directories, and do not accept a summary of one from anyone, including me. If
you see one by accident, say so rather than pretending you did not. An anchored
proposal that is disclosed is a recoverable problem; one that is hidden is not.

This is the mechanism, not the etiquette. Three genuinely independent reads are
the only reason this protocol is worth running. One glance collapses yours into
that read plus an anchoring effect, and phase 2 then critiques your agreement
instead of testing the idea.

The corollary that is easy to miss: propose what you actually think is best,
not what you think will survive critique. A defensive proposal converges on the
safe middle before the protocol has had a chance to do its work.

## Required output format

Four sections, all of them. A proposal missing one comes back to you.

**1. Approach.** What you would amend record 001 to say, and why this way
rather than the obvious alternative. Concrete enough that the other two can
attack it: name the plan record fields, the tool names and signatures, the
revalidation call per family, the failure states. "Generalize the plan" is not
attackable. "A `plan` record whose `operation` discriminator is one of
`action|alert_ack|report_run`, carrying a per-family `subject_fingerprint`
computed as ... , revalidated at apply by ... " is.

**2. Risks.** Where this breaks. What you are unsure about. What you would find
out first given one hour and one question against DEVEL. Include the risks that
make your own approach look worse. The other two will find them, and naming
them yourself costs nothing and makes phase 2 land somewhere more useful than
the thing you already knew.

**3. Division-of-labor claim.** Which piece you specifically are best suited to
own, and why. Not a commitment, and not a claim on the whole job. If a piece is
genuinely better suited to another resident, say so and say why; that sentence
is worth more to the synthesis than a confident claim on everything, because it
is the one I cannot write for you.

**4. Rough estimate.** Rough. Order of magnitude, honest unit. Say what would
blow it up. A padded estimate is less useful than a wrong one.

## Ship it as a commit

Write the proposal as a real file on your branch, under `docs/proposals/`,
named `<your-prefix>-worker-r2-mutation-gate-proposal.md`, and commit it. Not a
scratch file, not your dispatch output: a commit. The decision record will cite
it by full 40-character SHA, which is what makes the synthesis auditable
against what you actually proposed before you saw anyone else's.

Then report the full 40-character SHA and the branch. Your turn is not over
when the proposal is written. It is over when it is committed and the SHA is
reported.

Use the real output of `date -u` for any timestamp you write. Do not guess the
current time.
