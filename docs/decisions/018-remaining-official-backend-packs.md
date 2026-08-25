# 018: Carry the remaining official VCF backends as packs

- **Status:** accepted by principal directive
- **Date:** 2026-08-25
- **Assignment:** Add the remaining official VCF products as startup-frozen,
  endpoint-specific backend packs.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** principal directive, 2026-08-25: deliver the full VCF MCP
  specification, including the Wave 1a estate backends named in the governing
  2026-08-24 kickoff specification.

## Context

Decision 016 established the data-only pack model and proved it with VCF
Operations and vCenter. The appliance still omitted NSX, SDDC Manager, VCF
Operations for Networks, Fleet Lifecycle, SDDC Lifecycle, Log Management, and
vSAN Data Protection. Four additional product specifications are expected from
the operator later and are not present in the official source repository.

This is a directive-authority record. The principal already chose the product
set, endpoint-per-backend model, official specification source, and 19-tool
density. No worker proposal round was needed or authorized.

## Decision

Each remaining official product ships as its own unsigned data pack and gets
its own startup-frozen MCP endpoint only when a matching target exists. Every
new pack declares exactly 19 typed tools with frozen method, path, query, body,
projection, cap, and auth contracts. The live request path uses a static pack
runtime and does not import or call a generated SDK client.

The container adds explicit runtime auth strategies for HTTP Basic, a supplied
bearer token, SDDC Manager token acquisition, VCF Operations bearer acquisition,
VCF Operations service-token exchange, and vCenter session IDs. A 401 can cause
at most one reacquisition for schemes that support it. A 403 never retries.

Pack projections use declared field allowlists. The loader reads the official
built-in directory first, then may merge an operator-supplied directory through
the same validation. Operator packs cannot replace official identities and
cannot publish fewer than 19 tools. Avi, VCF Automation, Identity Broker, and
the software depot have reserved backend identities but no built-in packs until
their operator specifications arrive.

The runtime store advances to schema version 3 so the additional backend
identities can be registered through the admin UI. Existing rows and encrypted
credential envelopes migrate transactionally without decrypting or rewriting
their contents.

## Operational consequence

The appliance can publish one narrow endpoint for every official VCF product
in Wave 1a while retaining the same dispatcher and audit boundary. Fixture
tests prove pack loading, typed endpoint publication, auth request shapes,
projection allowlists, and operator-pack merging. Real appliance base paths,
authentication exchanges, permissions, and response shapes remain a lab gate
and are not claimed by this record.

## Constitution alignment

The overview paragraph of `CLAUDE.md` (and its generated copy `AGENTS.md`)
was aligned with this decision: product endpoints are derived at startup
from registered backends, any endpoint names in the overview are examples
rather than a fixed or exhaustive list, and `README.md` owns the current
per-product list. Firstmate approved this factual constitution alignment.
It is a documentation alignment only, not a captain or principal directive,
and it changes no rule or invariant.

## vCenter completion

Firstmate identified that the prototype-era vCenter pack still carried only
four tools. Firstmate directed this PR to remove that temporary exemption and
carry vCenter at the same density as the other products. All nine built-in
product packs now declare exactly 19 distinct tools. The vCenter list and get
operations remain separate contracts, each with its own frozen HTTP method,
path, query allowlist, and response projection.

## Review finding direction

Firstmate, not the captain, directed the implementation response to the four
external review findings. The captain had not seen or decided these findings.
Firstmate required the declared-backend client to strip upstream content
encoding and length headers when rebuilding an already decoded response,
restoration of the appliance field casing in both vCenter projections and
fixtures, restoration of the published `standalone` host filter with the
uncited UUID fields removed, and correction of the NSX segment placeholder.

## Protected paths touched

`src/vcf_ops_mcp/`

## Sign-offs

None. This implementation directly executes the principal's settled product
and safety requirements recorded above.
