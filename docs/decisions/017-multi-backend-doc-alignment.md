# 017: Align governing documents with the multi-backend product

- **Status:** accepted on Firstmate ruling, not yet captain-reviewed
- **Date:** 2026-08-25
- **Assignment:** Documentation pass for the multi-backend prototype
  (decision 016): bring the design contract and constitution into line
  with the captain's 2026-08-24 kickoff specification.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** Firstmate ruling, 2026-08-25, made on the captain's
  behalf; the captain has not reviewed this ruling. Applied verbatim: mark
  `docs/SPEC.md` as a historical contract superseded where it disagrees
  with the 2026-08-24 kickoff specification, correct only actively
  misleading constitution text, and record the supersession here.

## Context

Decision 016 shipped the multi-backend prototype under `src/vcf_ops_mcp/`
but covered only that path. The two other protected documents still
described the pre-prototype product: `docs/SPEC.md` (v1.0) specifies one
VCF Operations surface at `/mcp`, and `CLAUDE.md` (with its generated
twin `AGENTS.md`) described a single-product server and pinned the old
image name `ghcr.io/sentania-labs/vcf-ops-mcp`.

The governing kickoff specification of 2026-08-24 is not in this public
repository because it references internal material. That absence is the
root cause of the in-repo documentation drift this record closes.

## Decision

The product is multi-backend per the captain's 2026-08-24 kickoff
specification:

- Each registered product gets its own startup-frozen MCP endpoint:
  `/ops/mcp` for VCF Operations, `/vcenter/mcp` for vCenter Server, and
  `/vcf/mcp` for read-only management. An unregistered backend
  contributes no endpoint and no tools.
- Backends arrive as data-only packs carrying tool schemas, path
  templates, outbound method/query/body contracts, projections, caps,
  and a declared auth scheme, executed by static handlers through the
  mandatory dispatcher.

This supersedes the v1 SPEC precisely on these points: the single
`/mcp` VCF Operations surface (section on transport and deployment),
the single-product scope and naming (vcf-ops-mcp as an Operations-only
server), and the container image name (now
`ghcr.io/sentania-labs/vcf-mcp`). `docs/SPEC.md` itself receives only a
short header note stating the supersession; its body is unchanged and
remains the historical v1 record. Everything in the v1 SPEC not
contradicted by the kickoff specification remains in force.

`CLAUDE.md` is corrected only where its live instructions would now
actively mislead a worker: the project overview gains a short
multi-backend paragraph, the server-info self-description wording is
updated, and the pinned image name is fixed. `AGENTS.md` is regenerated
from `CLAUDE.md` by `tools/generate_agents_md.sh`, never hand-edited.

## Operational consequence

Workers read `docs/SPEC.md` as history, not as the live contract, on any
point the kickoff specification changed. Remaining stale SPEC body text
is handled by a future SPEC amendment, not by piecemeal edits.

## Protected paths touched

`docs/SPEC.md`, `CLAUDE.md`, `AGENTS.md`, `src/vcf_ops_mcp/`

The `src/vcf_ops_mcp/` code decision itself is recorded in decision 016;
it is listed here because this record and 016 land in the same pull
request and the consensus gate requires one record covering every
protected path that PR touches.

## Sign-offs

None. This documentation alignment rests on the Firstmate ruling
recorded above, made on the captain's behalf and not yet reviewed by
the captain; no worker proposal round ran.
