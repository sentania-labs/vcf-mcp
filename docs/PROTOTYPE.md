# Multi-backend prototype delivery note

This document is the proposed pull request body and the operator verification
packet for the VCF MCP prototype. It deliberately distinguishes fixture proof
from proof that requires Scott's lab.

## Summary

This change replaces the single `/mcp` VCF Operations surface with startup
composition for one management endpoint and a separate endpoint for every
built-in product:

- `/ops/mcp` exposes the 19 existing typed Operations read tools when an
  Operations target was registered before process start.
- `/vcenter/mcp` exposes 19 typed vCenter inventory reads when a vCenter target
  was registered before process start.
- `/nsx/mcp`, `/sddc-manager/mcp`, `/ops-networks/mcp`, `/fleet-lcm/mcp`,
  `/sddc-lcm/mcp`, `/log-management/mcp`, and `/vsan-dp/mcp` each expose 19
  typed read tools when their matching target was registered before process
  start.
- `/vcf/mcp` exposes only management, health, history, and skills reads.

Every product is carried by a separate unsigned, data-only backend pack. The
packs declare their product, tool schemas, paths, HTTP methods,
allowed query and body keys, projections, caps, and auth scheme. Tool handlers
are still static code, and a tool is published only after it is registered with
the mandatory dispatcher.

The admin UI supports target registration and editing for every built-in product.
An operator can change an existing target's name, FQDN, credentials, posture,
root CA, and TLS verification policy. Credential rotation and root CA storage
use the existing AES-256-GCM keyring path. The unsigned prototype refuses every
attempt to enable actions.

New targets default to TLS verification disabled, and the UI labels that risk
plainly. Trust is configured per target. Enabling verification cancels in-flight
requests on that target, as do root CA replacements and removal. It never
changes process-wide trust and never drains work that began under the replaced
trust.

API keys are scoped to endpoints, capabilities, and targets. Audit records now
carry endpoint name plus backend pack ID, SHA-256 digest, and version. Management
history is scoped to both key and caller identity, with no key-only fallback.

## Fixture evidence

The normal test suite performs no lab network calls. Its synthetic appliance
fixtures prove:

- one key calls a typed Operations tool on `/ops/mcp` and a typed vCenter tool
  on `/vcenter/mcp`, receiving projected product data from each
- Operations uses OpsToken authentication and vCenter uses Basic session
  creation followed by `vmware-api-session-id`
- a vCenter target sent to the Operations endpoint is denied and audited
- a missing backend contributes no product endpoint or tools at startup
- key revocation rejects the next request
- caller history returns nothing without `X-VCF-Caller-ID`
- target edits rotate credentials through the encrypted store
- CA plaintext, old credentials, and new credentials do not appear in SQLite
- enabling TLS verification selects request cancellation, not draining
- vCenter performs one bounded reauthentication on 401 and none on 403
- response projections discard undeclared upstream fields
- all nine built-in product packs publish exactly 19 distinct typed tools,
  without compressing or collapsing list and get operations
- Basic auth, SDDC token acquisition, Ops bearer acquisition, Ops token
  exchange, static bearer, and vCenter session auth are fixture-proven
- an operator-supplied 19-tool pack loads alongside the official set and cannot
  replace an official product pack

Run the proof with:

```sh
.venv/bin/pytest tests/
./tools/generate_agents_md.sh --check
./tools/consensus-check.py --self-test
```

## Phase plan and gates

This prototype is one delivery phase aimed at Gate 1. Local fixture proof and
packaging complete before the pull request opens. After deployment, Scott runs
the lab packet below. Gate 2 action work remains excluded because unsigned packs
cannot arm a target. Gate 3 remains a later production read-only registration.

## Operator verification still required

The following cannot be proven from this worktree because it cannot reach the
lab, and no lab credentials were requested:

1. Register each available devel appliance in the admin UI, then restart the
   container to freeze its product endpoint.
2. Upload the appropriate CA bundle for each, enable verification, and confirm
   one typed call returns real data from every registered product endpoint.
3. Confirm the bearer source for Fleet Lifecycle and SDDC Lifecycle, the
   Operations for Networks bearer flow, the Log Management exchange flow, and
   the exact SDDC Manager and vSAN session response shapes.
4. Call one tool from every implemented product, then confirm each attempt and
   terminal row identifies its endpoint and pack.
5. Revoke the key and confirm its next request is rejected.
6. Restart the container and confirm target credential decryption and audit
   continuity.
7. Restore the runtime database with the separately held keyring and confirm
   the same continuity.
8. Exercise the Streamable HTTP endpoints through the lab reverse proxy to
   check buffering, idle timeout, header forwarding, and reconnect behavior.

Until that packet is complete, compatibility with the real appliance versions,
base paths, authentication exchanges, lab CA chain, live permissions, response
shapes, reverse proxy, restart, and restore behavior remains unproven. The
worktree had no route to the captain's appliances, and no lab credentials were
requested or used.

## Deliberately deferred

This prototype must not be read as the completed product. The following are
plainly deferred production hardening:

- cosign pack signing, certificate identity pinning, the pack trust root, and
  trust-root refresh
- backend pack feed installation and rollback
- gateway mode and the authorization-mode toggle
- failed-auth circuit breaker
- upstream rate limiting and backoff
- response redaction
- token-budget warnings and install refusal

The backend definitions in this prototype load unsigned from disk. Unsigned is
the only supported prototype mode, and every action-enabled target is refused.
Certificate fingerprint pinning remains rejected. Uploaded CA bundles are the
TLS trust mechanism.
