# 015: retire the foundry operating model

- **Status:** accepted by direct authority
- **Date:** 2026-08-24
- **Assignment:** delete the retired foundry orchestration apparatus and strip
  every instruction that points at it
- **Lane:** direct captain instruction (no worker round)
- **Workers dispatched:** None (directive authority)
- **Authority:** a direct captain instruction, 2026-08-24: the foundry team
  that produced `TEAM-STATE.md` and the team-tracking directory (formerly
  `.team`, no longer present) no longer exists, so retire the apparatus rather
  than keep maintaining it, and remove the instructions in `AGENTS.md`/
  `CLAUDE.md` that still described operating as that team.

## Context

This project's constitution (`CLAUDE.md`, mirrored into `AGENTS.md`) was
written for a multi-agent foundry team: an orchestrator, three named worker
seats (`claude-worker`, `codex-worker`, `agy-worker`), a read-only critic seat
with a tiebreaker vote on a 2-2 four-ballot split, round-branch integration
with pre-integration sign-off markers, and role briefs injected from a
`roles/` directory. That team ran rounds 1 through 4 of this project and then
stopped existing.

The retirement left two separate problems, not one:

1. **Stale material that misled work.** The project's kickoff spec named
   `TEAM-STATE.md` as required reading, and a stale checkout of the
   predecessor repo caused an entire task to be dispatched against a critical
   path that had already been built.
2. **A constitution that still described a team that wasn't there.** Even
   after the stale files were gone, `AGENTS.md` and `CLAUDE.md` continued to
   instruct any agent working in this repo to behave as though the
   orchestrator/worker/critic apparatus were still running: assuming a
   worker's branch prefix, expecting a `roles/` brief that isn't in the repo,
   and treating a round-branch/sign-off-marker flow as the way changes reach
   `main`.

Both problems needed fixing for the constitution to describe reality.

## Decision

**Delete the retired apparatus, and rewrite the constitution to describe the
one-worker-per-task model that actually governs this repo now: one worker per
task, dispatched with a written brief, working on its own branch in an
isolated worktree, opening one pull request to `main`, reviewed before that PR
opens, then one external Codex review round on the PR with no re-review
loops.**

### Removed

- `TEAM-STATE.md` (1850 lines of retired orchestrator round history) and the
  team-tracking directory itself as a live directory (`markers/`, `blocked/`,
  `votes/`, `prompts/`, `signoffs/`, `provenance.md`, `team-config.yaml`, and
  the rest), other than the files relocated below.
- The `AGENTS.md`/`CLAUDE.md` section describing role briefs injected from a
  `roles/` directory, and the instruction to assume neither the orchestrator
  nor the worker role absent an injected brief. `roles/` was never checked
  into this repo.
- The workspace-conventions bullets describing per-resident branch prefixes
  tied to named doer seats, the cursor critic seat and its tiebreaker vote on
  a 2-2 four-ballot split, the round-branch integration model (doers
  committing to prefixed branches off one round branch that the orchestrator
  merges), and the pre-integration sign-off marker requirement.
- The reference to `TEAM-STATE.md` as the orchestrator's durable state file,
  and the `docs/decisions/TEMPLATE.md` field asking a new record to cite it.
- The word "resident" (foundry seat language) in the two remaining invariant
  statements that used it, replaced with "agent".

### Kept, because they are still true and load-bearing

- Decision records in `docs/decisions/` govern, and a new architectural
  decision gets a new record.
- Protected paths and `.github/protected-paths.txt`, and the requirement that
  a change touching one references a decision record.
- Branches and pull requests, never direct to `main`.
- One external Codex review round per PR, the sentania-labs convention, with
  no re-review loops.
- No lab credential in the repo, CI, logs, or transcripts, under any gating.
- Every project-specific technical fact in the file (VCF Ops invariants,
  read-only defaults, the prod hard-block, audit requirements, pinned
  tooling).

### Explicitly not carried forward as a guess

The retired constitution required every agent commit to carry a
`Co-authored-by:` trailer naming the resident that wrote it. That convention
was tied to the multi-resident foundry model, and whether it still applies
under one-worker-per-task is not something this record settles: the bullet
was dropped rather than kept on a guess. If it should still apply, that is a
deliberate addition, not a restoration.

## Where the historical evidence now lives

The rule applied here, after an earlier pass at this deletion missed it: any
material under the retired team-tracking directory that a decision record
cites is archived, not deleted; only material nothing in `docs/decisions/`
cites is deleted outright. Concretely, extracting every team-tracking-directory
path referenced anywhere in `docs/decisions/` at the branch point and checking
which of those paths actually existed there yields exactly these:

- `signoffs/` (all files): decision records 001 through 007 cite specific
  files here as the independently-checkable sign-off evidence for those
  decisions.
- `provenance.md`: the only surviving mapping from the git SHAs those records
  cite to the in-tree copies preserved under `docs/artifacts/`.
- `team-config.yaml`: decision record 007 cites it as evidence of the critic
  seating that made a tiebreaker vote unnecessary for that round's ballots.
- `votes/r3-critic-skills.md`: decision records 009 and 010 cite it as the
  critic's verbatim tiebreaking vote and reproduce it.
- `blocked/fleet-caddy-slot-config.md`: decision record 012 cites it as the
  blocker it closed out.
- `prompts/r4-assignment.md`: decision record 011 cites it as the scoping
  document for that round's assignment.

Every one of these is relocated, unedited, to `docs/history/`, preserving its
filename and relative path (so `signoffs/README.md` becomes
`docs/history/signoffs/README.md`, `provenance.md` becomes
`docs/history/provenance.md`, and so on). Each relocated file that serves as
its own directory's index carries an added note marking it archival and
pointing back to this record. The path citations in decision records 007,
009, 010, 011, and 012, and the sign-off citations in 001 through 007, are
updated to the new location so nothing dangles.

Everything else that lived under the retired team-tracking directory and that
no decision record cites (markers, prompts other than `r4-assignment.md`,
other votes, other blocked items) is deleted outright, not archived.

`docs/history/` is not a live process directory; nothing writes to it going
forward, and nothing in `AGENTS.md`/`CLAUDE.md` instructs an agent to use it.
It exists only so a signed decision record's evidence stays checkable.

## Dissent

None.

## Protected paths touched

CLAUDE.md
AGENTS.md

## Sign-offs

Directive-authority record: no worker round produced this change, so it
carries no worker sign-off lines. The `Authority` field above stands in their
place.
