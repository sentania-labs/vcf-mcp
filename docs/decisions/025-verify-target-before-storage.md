# 025: Verify target before storage

- **Status:** accepted by Captain directive
- **Date:** 2026-08-26
- **Assignment:** Implement GitHub issue 15, proving a submitted target
  credential reaches its backend before registration or an edit is stored.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** Captain 2026-08-26 decision recorded in sentania-labs/vcf-mcp
  issue 15.

## Context

The console previously encrypted and stored a target without contacting it.
Credential errors, DNS failures, connection failures, and certificate trust
failures appeared only on a later tool call, separated from the configuration
change that caused them.

This is a directive-authority record because the Captain selected strict
verify-before-storage behavior directly in issue 15. No worker proposal round
ran.

## Decision

Every backend pack declares one existing GET tool as its verification probe.
The pack therefore owns the product-specific choice of its cheapest safe read,
while the runtime continues to enforce the pack's frozen outbound contract.

The console builds a pending target configuration in memory, combines the
appliance CA and target-specific CA through the same additive order used for
normal calls, and runs the pack probe through the declared backend client. It
stores a new target or an edit only after the probe succeeds. A failed edit
leaves the prior host, credentials, trust, posture, and configuration
generation unchanged.

Verification has a 15 second whole-operation timeout. The console distinguishes
name resolution, connection, timeout, certificate trust, credential rejection,
and an unexpected reachable response. Probe attempts and terminal outcomes are
written to the durable audit ledger without credential material. A successful
timestamp is stored with the target and shown beside a manual recheck control.

The probe does not increment or clear the target authentication-failure
counter. It is read-only for every target, including a production-posture
target, and cannot reach an action path.

## Dissent

None. The implementation follows a direct Captain decision.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this decision, so it has
no worker sign-off lines. The `Authority` field above stands in their place.
