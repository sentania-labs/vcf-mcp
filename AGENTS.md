<!--
GENERATED FILE, DO NOT EDIT.

Produced from CLAUDE.md by tools/generate_agents_md.sh. CLAUDE.md is the one
canonical source for this constitution. To change anything below, edit
CLAUDE.md and re-run:

    tools/generate_agents_md.sh

Hand edits here will be overwritten and are flagged by CI.
-->

# CLAUDE.md, vcf-ops-mcp

Constitution for vcf-ops-mcp. Every agent working in this repo must honor
these rules.

## Project overview

vcf-ops-mcp is a container-based MCP server plus a small admin web UI for
VCF Operations (the Aria Operations / vRealize Operations lineage). It
exposes the VCF Ops suite-api as MCP tools over Streamable HTTP with
API-key auth: inventory/resources, metrics and super metrics, alerts and
symptoms, reports, and the actions framework (list action definitions,
populate/validate parameters, execute, poll async task status) with a
plan-then-apply confirmation model. It also serves operational skills
content two ways: as MCP resources/prompts for full clients and via
`list_skills`/`get_skill` tools for tool-calling-only consumers such as
VCF Private AI Services. VCF Ops targets (FQDN, credentials, auth source)
are post-deployment configuration entered through the admin UI, never
baked into the image or CI.

Since the multi-backend prototype (decisions 016 through 018), the server
is multi-backend: each registered product gets its own startup-frozen MCP
endpoint (for example `/ops/mcp` for VCF Operations, plus `/vcf/mcp` for
read-only management; `README.md` lists the full per-product set), and
backends are defined as data-only packs. `docs/SPEC.md` is the historical v1 design contract and
is superseded wherever it disagrees with the captain's 2026-08-24
kickoff specification (which lives outside this repo).

This is an unofficial, personal-lab project. Every endpoint's MCP
server-info self-describes as "Sentania ... (unofficial)". No agent
uses Broadcom or VMware branding in a way that implies this is an official
offering.

## This project's own invariants

- **No lab credentials or secrets ever enter this repo, CI, logs, or
  transcripts.** VCF Ops credentials, API keys, tokens, and session
  material are runtime data configured post-deployment through the admin
  UI and held in the server's encrypted-at-rest store on a volume. Tests
  use synthetic fixtures and mock endpoints. An agent about to commit,
  print, or echo anything resembling a real credential stops and asks; it
  does not "clean up" by force-deleting from history.
- **Read-only is the default posture, per target.** A newly registered
  VCF Ops target starts read-only. Action execution requires an explicit
  per-target enablement in the admin UI, and every action goes through
  plan-then-apply (the server returns a plan the client must confirm
  before execution). The read-only enforcement is structural: a read-only
  target's action-execution paths refuse server-side, regardless of what
  any client asks for.
- **The prod appliance is hard-blocked from actions.** The lab's
  production appliance (`vcf-lab-operations.int.sentania.net`) may only
  ever be registered read-only until Scott personally flips it. The devel
  appliance (`vcf-lab-operations-devel.int.sentania.net`) is the
  development and action-testing target.
- **Live-appliance access during development is read-only recon against
  devel only.** No agent executes actions against any live appliance
  until Scott's Phase 2 gate approval, and never against prod. Verifying
  an endpoint's shape by reading it from devel is allowed and encouraged;
  mutating anything on a live appliance is not.
- **Every tool call is audited.** Key identity, target, tool name, an
  args digest, and result status go to a durable audit log on a volume.
  No tool path ships without its audit write.
- **Knowledge sources are read-only inputs.** The vcf-content-factory and
  lab-admin repos (paths in `docs/SPEC.md`) are queried for API surface,
  lessons, and pitfalls. Portable knowledge only: do not copy their
  orchestration layers, `.env` contents, or lab-specific configuration
  into this repo.

## Style rule: no em-dashes

Do not use em-dashes anywhere. Not in code comments, not in docs, not in
commit messages. Use commas, periods, parentheses, or a plain hyphen instead.
This is a hard rule across the whole repo.

## Workspace conventions

- The default branch is `main`. Never commit directly to it. One worker per
  task, dispatched with a written brief, works on its own branch in an
  isolated worktree, and opens one pull request to `main`.
- No self-merge and no self-approval. The author of a change never merges it
  and never signs off on it as its own reviewer; it is reviewed before the PR
  opens.
- One external review round (Codex, per sentania-labs convention) on the PR.
  Its findings are addressed in the same PR, no re-review loops.
- Changes touching protected paths (enumerated in
  `.github/protected-paths.txt`) must reference a `docs/decisions/NNN-*.md`
  record. See `docs/decisions/README.md`.
- Escalate to the human principal rather than guessing: engine/runtime
  changes, architecture changes, new dependencies, anything that widens the
  action blast radius or weakens an invariant above, and edits to this
  constitution. Style, implementation detail, and refactors are the
  implementer's call.
- CI is fork-gated: PR jobs run only for branches pushed into this repo,
  never for forks.

## Pinned tooling

Python 3.12+. The MCP SDK/framework choice (FastMCP vs the reference MCP
SDK), the admin UI stack, and the credential-store encryption design are
round-1 architecture decisions, recorded in `docs/decisions/` before code
depends on them; do not pre-empt them by importing a framework in a
worktree ahead of the decision. CI builds one container image to
`ghcr.io/sentania-labs/vcf-mcp` on self-hosted runners and deploys to
the docker.int slot; deployment configuration (which is not credentials)
lives in repo Actions secrets per the CI-native standard.
