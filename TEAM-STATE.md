# TEAM-STATE

Orchestrator durable state for vcf-ops-mcp. Read this first on every run,
update it before exiting. This is machinery, not a human changelog.

## Current assignment

**Round:** 1 (the project's first round)
**Orchestrator run:** `orchestrator-run-20260720-223456`
**Cap:** 3600s

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

### Constraints

Beyond the constitution:

- No production code merges this round. Deliverable is decision records
  plus a phase-1 build plan. Spike/recon scratch may live in a worktree
  and does not merge.
- Scott's standing rulings are settled and are not re-litigated: the
  project name and unofficial self-description, docker.int slot behind
  fleet-caddy, devel-first with prod read-only later, Streamable HTTP +
  API keys, VCF credentials as post-deploy admin-UI configuration.
- CI's deploy job may slip to a later round: the lab-admin slot
  provisioning request is in flight and the handoff facts do not exist
  yet.
- Read-only recon against DEVEL only
  (`vcf-lab-operations-devel.int.sentania.net`). No mutations against any
  live appliance, and nothing at all against prod.
- No new dependencies beyond the round's framework decision without
  escalating to Scott.
- Knowledge directories are read-only inputs; portable knowledge only.

### Protected paths touched

Yes, expected:

- `docs/SPEC.md` (only if deliberation exposes a contract error)
- `src/vcf_ops_mcp/` (not this round; the records govern it prospectively)

The decision records themselves are the round's deliverable and are not a
protected path. Records that constrain `src/vcf_ops_mcp/` are written now
so that the Phase 1 build round has authorization to reference.

### Lane

**Full protocol.** Six genuine architecture forks where reasonable
engineers pick materially different approaches, and the outcome governs a
protected path (`src/vcf_ops_mcp/`). Nothing here is fast-lane eligible.

### Ballots

Contested synthesis questions use four ballots (orchestrator,
claude-worker, codex-worker, agy-worker). The critic (cursor) is invoked
only on a 2-2 split, per `.team/team-config.yaml`.

## Round mechanics

- **Round branch:** `round/1-architecture`, cut from `main` at `343be8c`.
- **Doer branches:** cut from the round branch.
  - `claude/round1-architecture`
  - `codex/round1-architecture`
  - `agy/round1-architecture`
- **Worktrees:** `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-<doer>`
- Doer branches are local-only and never reach `origin`.

## Phase log

| Phase | Status | Notes |
| --- | --- | --- |
| triage | done | full protocol, see Lane above |
| 1 blind proposal | running (attempt 1, alive) | codex + agy landed, claude in flight |
| 2 adversarial critique | pending | |
| 3 synthesis + records | pending | |

### Phase 1: attempt 1 was NOT dead. Correction, and a near-miss.

This run (`orchestrator-run-20260720-224036`) was dispatched with an
assignment stating as fact that run `...-223456`'s phase-1 dispatch was dead:
workers reaped at turn end, start markers `r1p1-*-20260720-223811` orphaned,
no processes, no proposal work. **That premise was false.** The attempt-1
workers were still running the whole time. Verified at 2026-07-20T22:43Z:

- `codex` ended 22:42:24Z, exit 0, `e89ee3a` -> `86b3404`, proposal committed
  at `docs/proposals/codex-worker-round1-architecture.md`, no uncommitted work.
- `agy` ended 22:42:35Z, exit 0, `e89ee3a` -> `68e30bd`, proposal committed
  at `docs/proposals/agy-worker-round1-architecture.md`, no uncommitted work.
- `claude` (pid 222810) still alive at 321s into its 1500s cap.

**The near-miss.** Acting on the false premise, this run dispatched a second
full set of three phase-1 workers into the same three worktrees at
22:42:13-17Z, concurrent with attempt 1. That is the exact worktree-collision
failure `dispatch.sh` warns about: two harness sessions in one worktree
corrupt each other. Caught within ~70s when the "end markers" the monitor
reported turned out to carry attempt-1 run ids (`...-223811`), not the new
ones. All three duplicate dispatch trees were killed by prompt-path match
(`/tmp/r1p1-*`), sparing pid 222810. Post-kill verification found no damage:
branch heads still at attempt 1's commits, all three worktrees clean.

Attempt 1's dispatch was also better formed than the duplicate: it passed
`-- --add-dir /home/scott/claude/vcf-content-factory --add-dir
/home/scott/claude/lab-admin`, giving workers the SPEC section 2 knowledge
directories. The duplicate omitted `--add-dir` entirely, so those workers
could not have read the research inputs at all. Any re-dispatch of a phase-1
or phase-2 worker MUST carry those `--add-dir` flags.

**Marker record.** Attempt 1's start markers were briefly quarantined under
the false premise and have been restored to their worktrees, so each end
marker has its pair. The three killed duplicates are quarantined at
`.team/markers/stale/r1p1-*-2242*-start.KILLED-DUPLICATE.md`. Those are the
files that are not live dispatches; the `...-223811` set is real.

**Lesson for the next run, stated as a rule.** A start marker with no end
marker means "unknown", not "dead". Before concluding a dispatch died, check
for a live process (`ps -eo pid,etimes,cmd | grep dispatch.sh`), not just for
markers. An orchestrator handed a confident premise about a dead dispatch
should still verify it, because re-dispatching over live workers is a strictly
worse failure than waiting.

## Notes for the next run

- This file lives on `main` deliberately. It is orchestrator state
  machinery in the same category as markers, and a next run that reads
  `main` first has to be able to find it.
- No dashboard/status-surface endpoint is configured in
  `.team/team-config.yaml` for this project, so the narration section of
  the orchestrator brief is skipped. Nothing to post to.
- The framework install is at `/home/scott/foundry/tools/team-framework`
  (`$TEAM_FRAMEWORK_DIR`), a sibling of the project checkout, not inside
  it.
