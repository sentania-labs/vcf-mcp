# 008: alerts are read-only in the MVP

- **Status:** accepted
- **Date:** 2026-07-21
- **Assignment:** vcf-ops-mcp Phase 1 build round: read-only tool families against DEVEL
- **Orchestrator run:** `vom-p1-20260721-194336`
- **Lane:** fast lane (directive authority, no worker round)
- **Workers dispatched:** None (directive authority)
- **Authority:** principal directive, 2026-07-21: "drop the alert mutation / 'acknowledge' requirement; alerts are READ-ONLY in the MVP. There is no acknowledge verb in the VCF Ops API and Scott is not entering action territory for alerts yet."
- **Resolves:** the escalation opened in record `007-mutation-gate-generalization.md`, section "Escalated to the principal"
- **Amends:** `docs/SPEC.md` section 4.1

## Why this record has no worker sign-offs

`docs/decisions/README.md` defines a directive-authority record: a change the
principal directed outright, rather than one the team proposed, critiqued, and
converged on. This is that category, and it is worth saying plainly why rather
than leaving it to the header line.

Record 007 escalated this question deliberately. The team established the fact
(there is no acknowledge verb) but refused to pick the remedy, because
`docs/SPEC.md` is the design contract and every substitute verb changed the
blast radius in a way that is the principal's call and not the team's. Three
options went up. Scott chose one. Asking the three doers to now ratify his
choice would be asking workers to sign a decision no worker proposed and no
worker had authority to make.

The fact underneath the ruling was, however, established by a full worker round,
and record 007 carries all three signatures on it. This record inherits that
evidentiary base rather than replacing it.

## Context

`docs/SPEC.md` section 4.1 listed the alerts tool family as "alerts, symptoms,
acknowledge (acknowledge counts as an action for gating purposes)".

There is no acknowledge verb in the VCF Ops API. codex-worker and claude-worker
found this independently during round 2 and the orchestrator verified it against
the OpenAPI before synthesis: the string `acknowledg` appears zero times in the
9.1 OpenAPI, and the real alert verb set is suspend, cancel, takeownership,
releaseownership, assignownership.

The nearest verb to what a VCF Ops operator means by acknowledging an alert is
`cancel`, which closes the alert outright. That is materially wider than SPEC's
wording implied, which is exactly why the team escalated instead of substituting.

## Decision

**Option 3 of the three presented in record 007: drop the alert mutation
requirement from the MVP. Alerts are read-only.**

Concretely, in `docs/SPEC.md` section 4.1:

- The alerts tool family reads `alerts: alerts, symptoms` and carries no
  mutation verb.
- The parenthetical "(acknowledge counts as an action for gating purposes)" is
  removed along with the verb it qualified.
- SPEC states positively that alerts are read-only in the MVP, and why, so that
  a later reader does not re-derive the missing verb as an oversight and
  helpfully add `cancel` back.

The alert mutation question is not decided against forever; it is out of the
MVP. Reopening it means a new record that names a real verb, states its blast
radius, and satisfies record 007's revalidation gate. `cancel` closing an alert
outright is a fact that survives this record and any successor to it.

## Consequences

- Record 007's generalized mutation gate loses one of the three families it was
  designed to cover. This does not weaken the gate: 007's `operation` enum is
  closed, and an unimplemented family is one fewer grantable scope, which is the
  posture record 001 and 003 already require.
- Per resolution 2 (grantable scopes derive from implemented capabilities),
  there is no alert mutation capability, so no alert action scope is grantable.
  This was already true in MVP; this record makes it true by contract rather
  than by schedule.
- Phase 1 is unaffected in scope. It was always read-only.

## Protected paths touched

- `docs/SPEC.md`

## Dissent

None. No worker round was run; see "Why this record has no worker sign-offs".
