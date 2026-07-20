# CLAUDE.md, vcf-ops-mcp

Role-neutral constitution for vcf-ops-mcp. Every resident of this repo
(human or agent, whatever role it is running under) must honor these rules.

## Role briefs are injected, never auto-loaded

This constitution is role-neutral on purpose. It says what is true for
everyone. It does not say what an orchestrator does, or what a worker does.

Role briefs live in the framework's `roles/` (`roles/orchestrator.md`,
`roles/claude-worker.md`, `roles/codex-worker.md`, and one per additional
harness this project seats). They are never auto-loaded by any harness. The
dispatcher injects the relevant brief at dispatch time.

If you are reading this file and no role brief was injected into your
session, you are a plain interactive session. Assume neither role. Do not act
as the orchestrator, and do not assume a worker's branch prefix or sign-off
obligations apply to you. Ask before taking action that a role brief would
otherwise govern.

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
baked into the image or CI. See `docs/SPEC.md` for the full deliverable
definition, tool families, phases, and gates.

This is an unofficial, personal-lab project. The server self-describes as
"Sentania VCF Ops MCP (unofficial)" in its MCP server-info. No resident
uses Broadcom or VMware branding in a way that implies this is an official
offering.

## This project's own invariants

- **No lab credentials or secrets ever enter this repo, CI, logs, or
  transcripts.** VCF Ops credentials, API keys, tokens, and session
  material are runtime data configured post-deployment through the admin
  UI and held in the server's encrypted-at-rest store on a volume. Tests
  use synthetic fixtures and mock endpoints. A resident about to commit,
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
  devel only.** No resident executes actions against any live appliance
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

- The default branch is `main`. Every dispatch uses a feature branch plus a
  pull request, except the round-branch model below.
- Branch prefixes are per-resident: `claude/*`, `codex/*`, `agy/*` (this
  project seats claude-worker, codex-worker, and agy-worker as its three
  doers, per Scott's standard doer-composition ruling; cursor is seated
  read-only as critic, tiebreaker-only on a 2-2 four-ballot split, see
  `.team/team-config.yaml`).
- Every commit an agent authors carries a `Co-authored-by:` trailer naming
  the resident that wrote it, so authorship survives squash merges.
- No self-merge and no self-approval. The resident that wrote a change never
  merges it and never signs off on it as its own reviewer. Merge authority
  belongs to the orchestrator.
- Before a doer's slice integrates, another resident (not the author) must
  review the diff in-worktree and write a pre-integration sign-off marker
  under `.team/signoffs/` (see that directory's README). No marker, no
  integration.
- Per the framework's round-branch integration model: doers commit to
  prefixed branches off one round branch, the orchestrator merges reviewed
  doer branches into it locally, and the round branch produces exactly one
  PR to `main` with one external review round (Codex, per sentania-labs
  convention: one review round satisfies the gate, no re-review loops).
- An external review (Codex) must pass, and its findings must be addressed
  in the same PR, before that PR merges.
- Changes touching protected paths (enumerated in
  `.github/protected-paths.txt`) must reference a `docs/decisions/NNN-*.md`
  record signed by every worker it names as dispatched. See
  `docs/decisions/README.md`.
- Escalate to the human principal rather than deciding as a team: engine/
  runtime changes, architecture changes, new dependencies, anything that
  widens the action blast radius or weakens an invariant above, and edits
  to this constitution. Style, implementation detail, and refactors are
  the team's call. See `roles/orchestrator.md`'s "Escalate" section.
- CI is fork-gated: PR jobs run only for branches pushed into this repo,
  never for forks.
- `TEAM-STATE.md` at repo root is the orchestrator's durable state file. It
  is read-and-updated machinery, not a human changelog.

## Pinned tooling

Python 3.12+. The MCP SDK/framework choice (FastMCP vs the reference MCP
SDK), the admin UI stack, and the credential-store encryption design are
round-1 architecture decisions, recorded in `docs/decisions/` before code
depends on them; do not pre-empt them by importing a framework in a
worktree ahead of the decision. CI builds one container image to
`ghcr.io/sentania-labs/vcf-ops-mcp` on self-hosted runners and deploys to
the docker.int slot; deployment configuration (which is not credentials)
lives in repo Actions secrets per the CI-native standard.
