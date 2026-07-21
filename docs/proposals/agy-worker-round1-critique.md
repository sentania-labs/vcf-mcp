# Round 1 Critique (agy-worker)

## Concessions

Before critiquing, I must explicitly concede three points where my peers' measured recon proved my proposal's estimates wrong:

1. **The blocker for dynamic tool generation is missing metadata, not tool count.** Both Claude and Codex correctly measured that `GET /api/actiondefinitions` returns no parameter metadata. The schemas must be fetched via `POST /api/actions/{id}/query` per context resource. This structural reality kills my "hundreds of definitions" context-explosion argument; generation is impossible without issuing POST storms against live resources just to build `tools/list`. They are right, and I was wrong.
2. **Streamable HTTP is natively supported via FastMCP.** My Risk 4 speculated that the reference SDK might not support Streamable HTTP natively and would require a custom adapter. Both peers correctly identified that the `mcp` package bundles `FastMCP`, which exposes `streamable_http_app()` returning a Starlette application that handles this seamlessly.
3. **The correct ASGI layer is FastMCP, not low-level SSE.** I proposed using `mcp.server.sse` directly. Codex correctly argues this adds unnecessary protocol plumbing, and Claude correctly leverages `FastMCP`'s `TokenVerifier` to perfectly map our API-key scope requirements.

## Critique of Claude's Proposal

**Steelman:** Claude accurately identifies the missing parameter metadata as the true blocker for dynamic tools. It cleverly leverages the reference SDK's transitive dependency graph to get `starlette` and `cryptography` for free, avoiding dependency escalations. It aggressively projects VCF Ops responses to solve the context window problem, and strictly limits API key scopes to `read_only` and `actions`.

**Attack:**
- **Server-side state for plans:** Claude acknowledges a TOCTOU hole in its `plan_action` design, but the bigger issue is storing plans server-side with a TTL. This introduces statefulness to the MCP layer, creates a memory leak vector, and stores credentials-adjacent data in memory. Codex's stateless signed plan token is the correct architecture here.
- **API Key Caching:** Claude proposes a 60-second in-memory cache for API keys to make revocation "immediate". A 60-second window where a revoked key can still execute a destructive infrastructure action is unacceptable. Every request gating an action must perform the constant-time digest check against the database.
- **Skills inside the image:** Claude argues for baking skills into the container image to prevent prompt injection via volume tampering. However, Phase 3 is entirely about an agent mining and hot-loading new skills. Forcing a container rebuild and redeploy for every typo fix or new skill an agent mines will strangle iteration and repository velocity. The runtime must be able to hot-reload skills.

## Critique of Codex's Proposal

**Steelman:** Codex builds a highly robust, stateless action execution pipeline. By returning a signed HMAC token to the client that encodes the parameters and digest, it avoids server-side state entirely. It also specifies strict AES-GCM credential encryption with AAD bindings to target IDs, correctly preventing ciphertext transplanting across environments.

**Attack:**
- **False Dependency Escalation:** Codex explicitly claims that `cryptography` is a new dependency requiring Scott's approval and escalation. As Claude correctly observed, `cryptography` is already a transitive dependency of the `mcp` package (via `pyjwt[crypto]`). Escalating a transitive dependency as a new architecture choice is a false premise and wastes the orchestrator's time.
- **Repository Churn for Skills:** Codex mandates a central `skills/index.yaml` and strict immutable semantic versioning (`skills/<slug>/<semver>/SKILL.md`) for all skills. While disciplined, this adds massive repository churn and friction for Phase 3, where an LLM agent will be generating these skills. A directory-scanning loader (like Claude's) is vastly better suited for agentic mining than forcing an agent to safely manage and resolve conflicts in a central YAML index.
- **Fragile Capability Probes:** Codex relies on capability probes at target registration but still pins its implementation to the offline OpenAPI examples. If an appliance is upgraded later, the probe must re-run to detect changes. However, as Claude's recon proved, the 9.0.2 appliance returns 404s for internal paths documented in the spec. Codex's reliance on static typing and registration-time probes will remain brittle against undocumented live-appliance drift compared to defensive parsing.

Co-authored-by: Antigravity <agy@team.local>
