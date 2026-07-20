# TEAM-STATE

Orchestrator durable state for vcf-ops-mcp. Read this first on every run,
update it before exiting. This is machinery, not a human changelog.

## Current assignment

**Round:** 1 (the project's first round)
**Orchestrator run:** `orchestrator-run-20260720-231633` (phases 2 and 3)
**Prior runs this round:** `...-223456` (phase 1 dispatch), `...-224036`
(duplicate-dispatch near-miss, corrected)
**Status:** deliverable complete, PR open, awaiting external review

### Goal statement (verbatim, as given)

> The project was bootstrapped today: constitution (CLAUDE.md), SPEC v1.0
> (docs/SPEC.md), team config, consensus tooling, repo at
> github.com/sentania-labs/vcf-ops-mcp (private, branch+PR strategy).
> Read CLAUDE.md and docs/SPEC.md first; they are the contract. This is
> the project's first round; there is no TEAM-STATE history yet.
>
> Scott's standing rulings, already made (do not re-litigate): name and
> unofficial self-description; deploy to a docker.int slot behind
> fleet-caddy (provisioning request to lab-admin is in flight, so CI's
> deploy job may land in a later round once the handoff facts exist);
> devel appliance first with prod read-only later; Streamable HTTP + API
> keys; VCF credentials are post-deploy admin-UI configuration.
>
> Run the full protocol (blind proposals, critique, ballots, synthesis,
> decision records) on the round's real architecture forks:
>
> 1. Static core MCP tools vs dynamic tool generation from the live
>    `GET /api/actiondefinitions` catalog, or a hybrid. Consider client
>    context cost, tool-count explosion, and what VCF Private AI Services
>    tolerates.
> 2. MCP framework: FastMCP vs the reference MCP Python SDK (or
>    another), for Streamable HTTP + API-key auth middleware.
> 3. Credential-store encryption design (app-managed key file on a
>    volume, algorithm/library, rotation story) and the API-key model
>    (scoping read-only vs actions-capable).
> 4. Admin UI stack (server-rendered minimal vs SPA; files-hosting's
>    session-auth pattern is the lab precedent).
> 5. Skills content model: how skills/ markdown is versioned, exposed as
>    resources/prompts AND as list_skills/get_skill tools, and how the
>    Phase 3 mining round will add to it.
> 6. API version drift handling: the lab appliance is 9.0.2, docs are
>    9.0/9.1. Read-only recon against the DEVEL appliance
>    (vcf-lab-operations-devel.int.sentania.net) is allowed and
>    encouraged to verify endpoint shapes, including its live
>    Swagger/OpenAPI if reachable; VCF-CF's OpenAPI JSONs are the offline
>    reference. NO mutations against any live appliance.
>
> Research inputs (read-only; portable knowledge only, per constitution):
> the knowledge directories and reference material enumerated in SPEC
> section 2, including vcf-content-factory's vcfops-api skill,
> client.py, api-surface recon docs, lessons/rules indexes, and the
> zw008/VMware-AIops repo for pattern comparison. The VCF 9.0 PDF is
> large; sample it purposefully, do not attempt a full read.
>
> Deliverable for this round: decision records under docs/decisions/
> resolving forks 1-6 (or escalating the ones that are genuinely
> Scott's), plus a phase-1 build plan recorded in TEAM-STATE.md, plus an
> amended SPEC only if deliberation exposes a contract error. No
> production code this round; spike/recon scratch under a worktree is
> fine but does not merge.

### Lane

**Full protocol.** Six genuine architecture forks governing a protected path
(`src/vcf_ops_mcp/`). Nothing here was fast-lane eligible. One unrelated
fast-lane item was triaged separately mid-round (see "Fast-lane fix" below).

## Phase log

| Phase | Status | Notes |
| --- | --- | --- |
| triage | done | full protocol |
| 1 blind proposal | **done** | three proposals, cross-doer blindness verified |
| 2 adversarial critique | **done** | three critiques, genuine attacks, real concessions |
| 3 ballots + synthesis | **done** | two questions, four ballots each, both 4-0 |
| records | **done** | 001-006 committed, signed by all three doers |
| integration | **done** | all doer branches merged into `round/1-architecture` |
| PR | **open** | PR #1, awaiting external Codex review |

## Round mechanics

- **Round branch:** `round/1-architecture`, pushed to origin.
- **PR:** https://github.com/sentania-labs/vcf-ops-mcp/pull/1
- **Worktrees:** `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-<doer>`

### Artifact SHAs (cited by the decision records)

| Doer | Proposal | Critique | Ballot | Signature + peer review |
| --- | --- | --- | --- | --- |
| claude-worker | `85cf712` | `6eb92bd` | `ab2570c` | `4cde29b` |
| codex-worker | `86b3404` | `5bc71c9` | `da6e6a5` | `dd9cf51` |
| agy-worker | `68e30bd` | `591cfb6` | `0a36659` | `9576887` |

All are merged into `round/1-architecture`, so the records' citations resolve
after the doer branches are deleted. **Do not delete a doer branch before
confirming its commits are reachable from the round branch.**

## What this round decided

Six records under `docs/decisions/`. Read them rather than this summary.

The round turned on measurement. claude-worker and codex-worker independently
ran read-only recon against DEVEL and converged on the same numbers: 142 action
definitions, all type `UPDATE`, **no parameter metadata in the list response**.
That structural fact is why dynamic tool generation is impossible, and it is a
stronger reason than the tool-count argument the assignment anticipated.
agy-worker reasoned from an unmeasured estimate and conceded in full.

Ballots were 4-0 on both contested questions (skills content model, keyring
co-location), so **the critic seat was correctly not invoked**. Per
`.team/team-config.yaml` cursor is tiebreaker-only on a 2-2 split.

## Escalations to Scott, open

None of these blocks the PR; all block Phase 1 or Phase 2 build work.

1. **Action authorization granularity** (001). Team recommends per-key
   action-class subsets intersected with a global policy, default empty.
2. **Minting actions-scoped keys before the Phase 2 gate** (001, 003). Team
   recommends no.
3. **Ratification of the keyring co-location residual risk** (003). 4-0 for
   Option A with three enforced separation controls; codex-worker and
   agy-worker held that Scott accepts the residual risk, not the team.
4. **The `jinja2` dependency** (004). Verified not transitive from `mcp`.
5. **A DEVEL API service account** (006). None exists for this project;
   claude-worker's recon borrowed vcf-content-factory's `devel` profile.

## Fast-lane fix taken mid-round

`tools/consensus-check.py:572` asserted `src/photoflow/`, a leftover from the
template repo the tooling was copied from, so `--self-test` failed and would
have blocked this round's own PR. Commit `67044f1` had claimed to fix exactly
this and fixed only one of two occurrences. Dispatched to codex-worker
(`a3e1a89`), peer-reviewed by claude-worker (`b2ec104`). Self-test now passes
and the full gate returns exit 0.

**Left for a later sweep, non-blocking:** claude-worker found that the comment
at `tools/consensus-check.py:516` still cites `001-town-motion.md`, another
template leftover. It is prose in a comment with no behavioral effect. The
`src/core/` and `ARCHITECTURE.md` strings elsewhere in that file are deliberate
synthetic fixtures, not leftovers, and must not be "fixed".

## Next run starts here

1. **Get the external Codex review on PR #1** and address its findings. The
   constitution requires one external review round before merge; per
   sentania-labs convention one round satisfies the gate, no re-review loops.
   Route substantive fixes to the owning doer and integrate signed commits
   locally. This is the only thing standing between the round and merge.
2. **Merge PR #1**, then delete `round/1-architecture` and all five local doer
   branches (three round branches plus `codex/fix-consensus-selftest` and
   `claude/fix-consensus-review`).
3. **Write the `.review-passed` marker straight to `main`**, not as its own PR.
4. **Put the five escalations above in front of Scott** before the Phase 1
   build round is scoped. Items 4 and 5 block build work directly.

### Retained on purpose

Five local doer branches are retained because PR #1 is not merged: the three
round-1 branches plus `codex/fix-consensus-selftest` and
`claude/fix-consensus-review`. All are merged into the round branch. None is on
origin, and none may be pushed there. Delete them at merge, per step 2.

## Notes for the next run

- **The phase-1 near-miss, and the rule it produced.** Run `...-224036` was
  handed a confident premise that the phase-1 dispatch was dead and acted on
  it, dispatching a second full set of workers into the same three worktrees
  concurrently with live attempt-1 workers. A start marker with no end marker
  means "unknown", not "dead". Check for a live process
  (`ps -eo pid,etimes,cmd | grep dispatch.sh`) before concluding a dispatch
  died. Re-dispatching over live workers is strictly worse than waiting.
- **That kill was not as complete as the previous run recorded.** This run
  found that two duplicate workers survived the 22:43 kill and committed
  afterward: claude at `0ddea54` (22:51:33Z) and codex at `51e02f7`
  (22:45:54Z), both above their attempt-1 heads. The previous run's "no damage"
  verification was taken too early to see them. The duplicates were dispatched
  **without** `--add-dir`, so they could not read the SPEC section 2 knowledge
  directories, and claude's duplicate reached a materially weaker factual base
  (it reported a 401 and no live recon where attempt 1 measured 142 action
  definitions). Attempt-1 commits were therefore taken as canonical, branches
  were reset to them, and the duplicates are preserved at tags
  `archive/r1p1-claude-duplicate` and `archive/r1p1-codex-duplicate`.
  **Verify a kill by re-checking branch heads a few minutes later, not
  immediately.**
- **Cross-doer blindness was verified, not assumed.** Each doer branch's full
  file history was walked to confirm no branch ever contained a peer's proposal
  file. It did not. The duplicate contamination was intra-doer only, which is
  why phase 1 stood rather than needing a re-run.
- **Workers get `--add-dir /home/scott/claude/vcf-content-factory --add-dir
  /home/scott/claude/lab-admin`.** A worker without them cannot read the SPEC
  section 2 research inputs. Every dispatch this run carried them.
- **Marker timestamps are not always trustworthy.** claude-worker's phase-3
  signature and review markers both record `2026-07-20T23:38:12Z`, but the
  commit landed at `23:33:43Z`, about 4.5 minutes in the future. The signature
  is valid (the commit is real and git's commit time is authoritative), but
  prefer the git commit time over a self-reported marker time. The follow-up
  dispatch explicitly told the worker to read `date -u` and its next marker was
  accurate, so instructing it works.
- **Verify by end marker, never exit code.** Every dispatch this run was
  verified on `branch_sha_before`/`after`, `uncommitted_work`, and
  `cap_expired`. agy-worker's phase-2 marker reported `uncommitted_work: yes`;
  inspection showed untracked `scratch/` holding its read copies of the peer
  proposals, which is permitted worktree scratch and does not merge.
- **Dispatches are fast in this project.** Phase 2 took 224s wall clock for
  three parallel workers, phase 3 ballots 62s, sign-offs 75s. Caps of 900s and
  600s were never approached. Budget generously for synthesis and writing
  instead, which is where this run's time actually went.
- No dashboard/status-surface endpoint is configured in
  `.team/team-config.yaml`, so the narration section of the orchestrator brief
  is skipped. Nothing to post to.
- The framework install is at `/home/scott/foundry/tools/team-framework`
  (`$TEAM_FRAMEWORK_DIR`), a sibling of the project checkout, not inside it.
- This file lives on `main` deliberately, so a next run that reads `main` first
  can find it.
