# 023: Server-rendered admin console tabs

- **Status:** accepted by Captain directive
- **Date:** 2026-08-26
- **Assignment:** Implement GitHub issue 12, breaking the growing admin console
  into tabs on one page without changing operational behavior.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** Captain 2026-08-26 decision recorded in sentania-labs/vcf-mcp
  issue 12.

## Context

The administration dashboard had nine operational areas in one long page.
Every new capability increased scrolling and made it harder for an operator to
return to the relevant control after a configuration action. The Captain
selected tabs on one page instead of separate routes.

This is a directive-authority record because the Captain selected the
presentation model directly. No worker proposal round ran.

## Decision

The dashboard uses six server-rendered areas: Overview, Targets, API keys,
Packs, Maintenance, and Audit. The selected area is carried in the `tab` query
parameter on `/admin`. Unknown values safely render Overview. Each tab is a
normal link and the server renders the selected content, so navigation requires
neither JavaScript nor a healthy MCP surface.

Admin actions that redirect to the dashboard name their owning tab in the
redirect URL. Validation failures rendered in place also select the owning tab.
The existing forms, routes, CSRF checks, and recent-authentication gates remain
unchanged.

The Audit tab retains the dashboard's recent configuration-event summary. The
full MCP tool-call audit remains at `/admin/audit` because it is an established,
independently useful read page with existing deep links. The Audit tab links to
that page, and the existing header link remains valid.

## Dissent

None. The implementation follows a direct Captain decision.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this decision, so it has
no worker sign-off lines. The `Authority` field above stands in their place.
