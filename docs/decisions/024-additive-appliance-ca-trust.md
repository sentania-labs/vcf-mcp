# 024: Additive appliance CA trust

- **Status:** accepted by Captain directive
- **Date:** 2026-08-26
- **Assignment:** Implement GitHub issue 13, adding an appliance-wide CA that
  remains additive with every target-specific CA.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** Captain 2026-08-26 decision recorded in sentania-labs/vcf-mcp
  issue 13.

## Context

One internal CA can sign every appliance in a lab, but the runtime store only
accepted a CA on each individual target. Operators had to duplicate the same
certificate across existing registrations and every new registration.

This is a directive-authority record because the Captain selected the trust
behavior directly in issue 13. No worker proposal round ran.

## Decision

The runtime database stores one appliance CA bundle as configuration. It is
covered by the existing database backup and restore procedure and by the same
authenticated, recently reauthenticated, CSRF-protected, audit-required console
boundary as other governance changes.

Effective trust is assembled without a live request. It starts with the
appliance CA and appends the target-specific CA when present. The resulting
bundle is passed to the existing verified TLS context builder, which retains
system roots and never disables verification. Stored target CAs remain
unchanged.

The console identifies the appliance and target-specific trust sources for
each target by SHA-256 certificate fingerprint. Removal requires explicit
confirmation beside a list naming every target that will lose appliance trust.
Setting, replacing, and removing the appliance CA cancel cached backend clients
so the next request builds a client from current trust.

Submitted bundles must parse completely as PEM CA certificates before the
runtime database changes. Certificate fingerprint pinning is not introduced.

## Dissent

None. The implementation follows a direct Captain decision.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this decision, so it has
no worker sign-off lines. The `Authority` field above stands in their place.
