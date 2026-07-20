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
| 1 blind proposal | pending | |
| 2 adversarial critique | pending | |
| 3 synthesis + records | pending | |

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
