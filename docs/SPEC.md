# SPEC, vcf-ops-mcp (v1.0)

> **Historical note (2026-08-25).** This v1 design contract is superseded
> on any point where it disagrees with the captain's 2026-08-24 kickoff
> specification for the multi-backend vcf-mcp product. See
> `docs/decisions/017-multi-backend-doc-alignment.md`.

An unofficial, container-based MCP server plus small admin web UI for VCF
Operations, deployed on the lab's docker.int container host behind
fleet-caddy at `https://vcf-ops-mcp.int.sentania.net`. Comparable in
capability class to zw008/VMware-AIops (which targets vCenter via
pyVmomi), but built on the VCF Operations suite-api, including the
actions framework. This SPEC is the design contract; changes to it are
protected-path changes.

## 1. Purpose

Give MCP clients (Claude Code sessions, lab agents, later VCF Private AI
Services / Agent Builder) a governed tool surface over VCF Operations:
query inventory, metrics, alerts, and reports; trigger VCF Ops actions
with confirmation and audit; and pull operational skills content. The
server is a distribution point for VCF operational knowledge, not just an
API wrapper.

## 2. Inputs and reference material

Documentation (read as needed, do not commit copies of the PDFs):
- `~/claude/lab-admin/docs/vmware-cloud-foundation-9-0.pdf` (VCF 9.0, 148 MB)
- `~/claude/lab-admin/docs/vendor/vsphere-9-1/` (vSphere 9.1, extracted
  markdown chapters + INDEX; prefer this over the raw PDF at
  `~/claude/lab-admin/tmp/vmware-vsphere-9-1.pdf`)
- `~/claude/lab-admin/docs/vendor/private-cloud-mgmt/` (~25 files on VCF
  Ops metrics, capacity, super metrics, cost)

Reference implementation to study (patterns, not product target):
- https://github.com/zw008/VMware-AIops
  Borrow: structural read-only/read-write tool stripping, plan-then-apply
  for impactful actions, audit logging, progressive tool-doc disclosure.
  Diverge: suite-api not pyVmomi; bearer-token lifecycle auth; two-step
  metadata-driven actions; dynamic tool generation potential from
  `GET /api/actiondefinitions`.

Knowledge directories to query (read-only; portable knowledge only):
- vcf-content-factory (`~/claude/vcf-content-factory/`):
  - `.claude/skills/vcfops-api/` (auth token acquire, `Authorization:
    OpsToken`, public vs `/internal/*` + `X-Ops-API-use-unsupported`,
    failure modes; `references/api-surface-map.md`, `wire-formats.md`)
  - `src/vcfops_common/client.py` (reference client with 401 re-auth)
  - `knowledge/context/api-surface/` (20 recon docs, verified against the
    live 9.0.2 lab; start with `vcf_operations_api_surface.md`)
  - `reference/docs/operations-api{,-9.1}.json`,
    `internal-api{,-9.1}.json` (OpenAPI)
  - `knowledge/lessons/INDEX.md`, `knowledge/rules/INDEX.md`,
    `knowledge/context/investigations/`
- lab-admin (`~/claude/lab-admin/`): `.claude/skills/` (operational
  playbooks), `docs/sops/`, `docs/operations/` (dated pitfall journal),
  `docs/lab-map/topology.md`, `lab-config.json` (FQDN inventory)

## 3. Lab targets

- DEVEL (development + action testing):
  `vcf-lab-operations-devel.int.sentania.net`
- PROD (read-only, added at Gate 3, actions hard-blocked):
  `vcf-lab-operations.int.sentania.net`
- The lab appliance runs 9.0.2; docs cover 9.0/9.1. Verify endpoint
  shapes against live devel (its Swagger/OpenAPI) rather than trusting
  9.1 docs blindly; record drift findings.

## 4. Deliverable

One container image (plus compose file) providing three surfaces on one
listener behind fleet-caddy TLS:

### 4.1 MCP endpoint
- Transport: Streamable HTTP (SSE fallback optional). Auth: API keys
  minted/revoked in the admin UI, sent as bearer. Per-key scope:
  read-only or actions-capable.
- MVP tool families:
  - targets: list registered targets and their capability posture
  - auth/session: token lifecycle per target (acquire, refresh on 401),
    invisible to clients
  - inventory/resources: adapter kinds, resource kinds, resource query
  - metrics: stats/latest queries, super metrics
  - alerts: alerts, symptoms
  - reports: list/run/download
  - actions: list actiondefinitions, populate/validate parameters for a
    target resource, plan (dry summary of what would run), apply
    (execute), poll task status
- Alerts are read-only in the MVP. The API has no acknowledge verb, and
  the nearest substitute, `cancel`, closes an alert outright with a wider
  blast radius than the original wording implied.
- Static core tools vs dynamic generation from the live action catalog
  (or a hybrid) is a round-1 architecture decision.

### 4.2 Skills surface
- Skills are versioned markdown content in this repo (`skills/`),
  exposed BOTH as MCP resources/prompts (full clients) AND via
  `list_skills`/`get_skill` tools (tool-calling-only consumers such as
  VCF Private AI Services).
- Seed skills at MVP: suite-api auth walkthrough, actions how-to,
  metrics query patterns. Grown in Phase 3 from mined lab knowledge.

### 4.3 Admin UI
- Small session-authenticated web UI (bootstrap admin credential
  provisioned at first deploy, stored hashed; files-hosting is the
  precedent): register/edit VCF Ops targets (FQDN, credentials, auth
  source, verify-SSL), per-target read-only/actions toggle (prod
  hard-block per constitution), mint/revoke MCP API keys, view audit
  log.
- Target credentials live in an encrypted-at-rest store on a volume
  (app-managed key file, 0600). Never in the image, repo, or CI.

### 4.4 Audit log
- Every MCP tool call: timestamp, key identity, target, tool, args
  digest, result status. Durable on a volume, viewable in the admin UI.

## 5. Explicitly out of v1

- NSX, VCFA/automation, and direct-vCenter tools. The target-registry
  design must not preclude adding other target types later; Phase 3's
  knowledge-mining round proposes the v2 tool set (NSX, VCFA automation,
  logs via VCF Ops).
- PII/data scrubbing before external LLM consumption (documented known
  limitation).
- External (non-lab) exposure. Internal-only behind fleet-caddy.
- MCP sampling/elicitation features.

## 6. Phases and gates

- Phase 1: server skeleton, target registry + encrypted credential
  store, token lifecycle, read-only tool families verified against
  DEVEL (read recon allowed), minimal admin UI, CI build to
  ghcr.io/sentania-labs/vcf-ops-mcp + slot deploy.
  - Gate 1 (Scott): connect Claude Code to
    `https://vcf-ops-mcp.int.sentania.net` with a minted key, run read
    queries against devel.
- Phase 2: actions pipeline (plan-then-apply, async task polling),
  API-key scoping, audit log complete, admin UI action toggles.
  - Gate 2 (Scott): approve and run one real action round-trip on devel.
- Phase 3: skills surface complete; knowledge-mining round over
  lab-admin skills/sops/operations journal and vcf-content-factory
  lessons/investigations to propose the next tool set and new skills.
  - Gate 3 (Scott): prod registered read-only.

## 7. Deployment

- CI-native: GitHub Actions on self-hosted runners, test + build one
  image to ghcr.io/sentania-labs/vcf-ops-mcp, deploy job to the
  docker.int slot over the slot deploy key held in repo Actions secrets
  (ai-log-depot is the reference pipeline). Fork-gated.
- Slot: docker.int, fleet-caddy per-slot conf.d, DNS
  `vcf-ops-mcp.int.sentania.net`, volumes for the credential store and
  audit log. Provisioned by lab-admin under the container-host contract.
- Post-deploy configuration (targets, credentials, keys) happens only in
  the admin UI. CI never carries VCF credentials.
