---
blocked_run: gh-issue-2-execution-20260724-215456
role: orchestrator
raised_by: agy-worker (spike 002), confirmed by the orchestrator
timestamp: 2026-07-24T22:40:00Z
blocks: the delivery slice's end-to-end proxy verification, and Gate 1
severity: does not block the rest of the build
resolved: 2026-07-27
resolved_by: gh-issue-4-execution (round 4)
---

> **RESOLVED 2026-07-27.** fleet-caddy now terminates TLS for
> `vcf-ops-mcp.int.sentania.net` and answers `503` rather than dying at Client
> Hello, which is the signature of a routed slot with no backend behind it.
> Verified by the orchestrator this round:
> `curl -k -o /dev/null -w '%{http_code}' https://vcf-ops-mcp.int.sentania.net/healthz`
> returns `503`. The remaining 503 is the application defect tracked as issue
> #5, not a routing gap. Kept in place rather than deleted, per the marker
> convention; the text below is the original block as raised.

# BLOCKED: fleet-caddy has no per-slot config for this project

## What is needed

lab-admin (or the principal) must complete the docker.int slot handoff for
vcf-ops-mcp by supplying the **fleet-caddy per-slot configuration** that routes
`vcf-ops-mcp.int.sentania.net` to this project's slot backend and terminates
TLS for it.

## What was measured, on day one, exactly as the workplan ordered

agy-worker ran workplan step 0 spike 002 and stopped at the blocker rather than
substituting a local proxy, which is what it was told to do and the right call.

- **DNS exists.** `vcf-ops-mcp.int.sentania.net` resolves via CNAME to
  `docker-proxy.int.sentania.net` (172.16.3.33).
- **The slot config directory exists and is empty.**
  `docker exec fleet-caddy ls -la /etc/caddy/conf.d/vcf-ops-mcp` shows nothing
  in it.
- **The proxy therefore drops the connection during the TLS handshake.**
  `curl -vI https://vcf-ops-mcp.int.sentania.net` connects on 443 and fails with
  `SSL_ERROR_SYSCALL` at Client Hello.
- `DOCKER_DEPLOY_KEY` is present in repo Actions secrets, so the deploy half of
  the handoff did land. It is the caddy half that is missing.

## Why this matters more than a missing config file usually would

The workplan named this exact dependency as the delivery slice's largest risk
and ordered the spike on day one specifically so it would fire now rather than
in week two. It fired. That is the spike working, not the plan failing.

The consequence is that **the one question the spike existed to answer is still
unanswered**: whether a Streamable HTTP MCP session survives this proxy intact,
under response buffering, idle timeouts, and auth-header forwarding. Nothing
local can answer it. Until it is answered, the delivery slice proceeds on an
unverified assumption about its own transport, and Gate 1 rests on that
assumption too.

## What is NOT blocked

Everything else. The spine, the read plane, `contracts.py`, skills, and the
admin UI all proceed. The blocker is scoped to the proxy path and to Gate 1's
final connect step.

## Resolution

Escalated to the principal on GitHub issue #2. When the config lands, re-run
spike 002 before the delivery slice's deploy work is considered verified.
