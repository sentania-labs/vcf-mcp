# Spike 002: Streamable HTTP through fleet-caddy

**Verdict: BLOCKED.** The lab handoff facts do not fully exist yet. The fleet-caddy per-slot configuration for this project is missing, making it impossible to test proxy behavior. This is a hard blocker that requires escalation to lab-admin before the Streamable HTTP proxy smoke test can proceed.

## Question 1: Do the lab handoff facts exist yet?
No, they are incomplete.
* **DNS Resolution:** Yes. `vcf-ops-mcp.int.sentania.net` successfully resolves to the proxy host (`docker-proxy.int.sentania.net` / `172.16.3.33`).
* **Docker Slot:** The directory for the slot's configuration exists inside the Caddy container (`/etc/caddy/conf.d/vcf-ops-mcp`), but it is entirely empty.
* **Fleet-Caddy Config:** **Missing.** Because the per-slot Caddy config is absent, the proxy drops connections to this host during the TLS handshake (`SSL_ERROR_SYSCALL` upon Client Hello).

Evidence gathered:
* `dig vcf-ops-mcp.int.sentania.net` successfully resolved the CNAME to `docker-proxy.int.sentania.net`.
* `curl -vI https://vcf-ops-mcp.int.sentania.net` successfully connects on port 443 but immediately drops the connection during the TLS handshake.
* Connecting to the docker host directly and inspecting the `fleet-caddy` container (`docker exec fleet-caddy ls -la /etc/caddy/conf.d/vcf-ops-mcp`) confirmed the configuration directory is completely empty.

## Streamable HTTP Behavior (Buffering, Idle Timeout, Header Forwarding)
**Not tested.**
Because the proxy does not have a configuration to route traffic or terminate TLS for this project, no requests can reach a backend container. Testing proxy behavior such as response buffering, idle timeouts, and header forwarding is structurally impossible until the Caddy configuration is provided.

## Reconnect Behavior
**Not tested.** 
Cannot be evaluated without a functional proxy routing to a backend.

## Impact on the Delivery Slice
This is a hard blocker for the end-to-end proxy test, and per the workplan, this was the delivery slice's largest risk. The delivery slice is currently blocked on lab-admin completing the handoff (providing the fleet-caddy per-slot config). The Streamable HTTP test must be re-run once the config exists to determine if proxy buffering or timeouts will require architecture changes to the MCP transport layer. This reorders the delivery slice: we cannot safely proceed assuming the proxy will pass Streamable HTTP intact until this is actually measured.

## Clean Up
No throwaway container was deployed because the absence of the proxy configuration made doing so pointless, and no local test infrastructure was spun up per the instruction to test the real proxy only. Nothing to clean up.
