# VCF Ops MCP - Round 1 Architecture Proposal

Co-authored-by: Antigravity <agy@team.local>

## 1. Per-fork positions

### Fork 1: Static core MCP tools vs dynamic tool generation
**Position:** Hybrid approach. We provide a static core set of tools for reads (e.g., `get_resource`, `query_metrics`, `list_alerts`) and a fixed pair of tools for actions: `plan_action` and `apply_action`. The available actions catalog is exposed as an MCP resource (e.g., `vcf-ops://action-catalog`) rather than exploding them into individual MCP tools.
**Reasoning:** As noted, VCF Private AI Services truncates tool lists if they grow too large. Given the sheer number of possible actions and combinations in VCF Ops, generating one tool per action will quickly blow past context limits and trigger truncation. A static `plan_action(action_id, params)` tool keeps the tool list small and predictable, while forcing the client to read the resource catalog to discover `action_id`s.
**Alternative rejected:** Dynamic tool generation from `GET /api/actiondefinitions`. While convenient for clients that support infinite tools, it is too fragile against LLM context windows and truncation limits imposed by downstream consumers.

### Fork 2: MCP framework
**Position:** Reference MCP Python SDK.
**Reasoning:** We need strict, custom middleware for Streamable HTTP, API-key authentication, and robust audit logging to a durable volume. The reference SDK integrates cleanly with Starlette/FastAPI, allowing us to drop in standard ASGI middleware to handle API-key validation and inject the read-only vs actions-capable scope into the request state *before* it reaches the MCP router.
**Alternative rejected:** FastMCP. While it provides ergonomic decorators, it hides the ASGI routing layer, making it harder to implement custom auth middleware, early-rejection for read-only keys, and structured audit logging without hacking the internals.

### Fork 3: Credential-store encryption & API-key model
**Position:** App-managed Fernet key on a volume with hashed API keys.
**Reasoning:** 
- **Encryption:** We generate a Fernet symmetric key (from the `cryptography` package) on first boot, stored in a 0600 file on the volume. The admin UI uses this to encrypt/decrypt target credentials (username/password/host) before writing to the local config store (e.g., SQLite or JSON). 
- **API Keys:** API keys minted by the admin UI are stored locally as bcrypt hashes. The key payload contains the scope (`read-only` or `actions-capable`). The middleware verifies the hash and enforces the structural read-only block.
**Alternative rejected:** Vault or external KMS. Overkill for a lab project. We also reject storing API keys in plaintext, adhering to standard security practices.

### Fork 4: Admin UI stack
**Position:** Server-rendered minimal HTML (Jinja2 + FastAPI/Starlette) with session cookies.
**Reasoning:** The lab precedent is files-hosting's session-auth pattern. A minimal server-rendered app served by the same Python process that runs the MCP server minimizes moving parts. No npm build step, no separate SPA container, and trivial integration with the Python credential store.
**Alternative rejected:** A Clarity-based SPA. While it matches the VCF Ops aesthetic, it introduces an entirely separate toolchain (Node/npm) and build complexity for an interface that only needs a few forms (register target, toggle actions, mint API key).

### Fork 5: Skills content model
**Position:** Flat Markdown files injected as both MCP Resources and Tools.
**Reasoning:** Skills live in `skills/*.md` with YAML frontmatter. The server loads these on startup.
- For full clients: Served as MCP resources (`skill://name`) and Prompts.
- For tool-only consumers: Served via a static `list_skills` and `get_skill(name)` tool.
In Phase 3, the mining round will simply open PRs to drop new `.md` files into the `skills/` directory, which the server will pick up on restart.
**Alternative rejected:** A database-backed skills model. Skills are code-adjacent knowledge; they belong in version control, benefiting from PR reviews before they affect agent behavior.

### Fork 6: API version drift handling
**Position:** Trust DEVEL's live schema, use defensive parsing.
**Reasoning:** The docs claim 9.1 shapes, but the lab runs 9.0.2. Our recon shows discrepancies (e.g., `/suite-api/internal/adapterkinds` returning 404). We will write Pydantic models for responses with `extra='ignore'` to tolerate new fields, and we will code against the live DEVEL endpoint behavior rather than the offline OpenAPI spec.
**Alternative rejected:** Strict OpenAPI client generation. Auto-generating a client from the 9.1 spec will break immediately on 9.0.2 due to missing internal endpoints and drift.

## 2. Phase-1 build plan

1. **Foundation & CI:** Setup FastAPI + MCP SDK skeleton. Configure GitHub Actions for fork-gated CI building `ghcr.io/sentania-labs/vcf-ops-mcp`.
2. **Security & Storage:** Implement the encrypted-at-rest credential store (Fernet) and the bcrypt API-key registry. Implement the ASGI auth middleware.
3. **Admin UI:** Build the minimal Jinja2 server-rendered admin UI (login, mint keys, register targets).
4. **VCF Client:** Implement the base `VCFOpsClient` (handling `/api/auth/token/acquire`, token refresh, and SSL verify) targeting DEVEL.
5. **Read-Only MCP Tools:** Implement the MVP read tools (`targets`, `inventory`, `metrics`, `alerts`, `reports`) using the `VCFOpsClient`.
6. **Skills Surface:** Implement the `skills/` loader, exposing them as resources, prompts, and `list/get` tools.
7. **Audit Logging:** Implement the durable audit log middleware recording every tool invocation.
8. **Deferrals:** 
   - Action execution (plan-then-apply) is explicitly deferred to Phase 2.
   - Any write/mutation tools are deferred.
   - Prod target registration is deferred to Gate 3.

## 3. Risks

- **Risk 1:** The `VCFOpsClient` session cookie/token lifecycle might interact poorly with the Streamable HTTP long-lived connections, causing silent timeouts if tokens expire mid-stream and aren't properly refreshed by the SDK transport.
- **Risk 2:** Private AI Services might still choke on large text payloads from read-only tools if we don't aggressively paginate or filter (e.g., a massive `alerts` response).
- **Risk 3 (Self-Sabotage):** By choosing server-rendered HTML over an SPA, the admin UI might feel clunky or lack dynamic validation, which could be annoying for complex target registration.
- **The one question I would answer first:** Given an hour, I would write a quick script against DEVEL to test if `OpsToken` expiration mid-request cleanly returns a 401 that our client can catch and retry, or if it drops the connection.

## 4. Division-of-labor claim

- **My strengths (Antigravity):** I am best suited to build the **Python SDK / FastAPI middleware** (auth, audit logging, Fernet encryption). Gemini models excel at writing robust, defensive Python backends and handling ASGI middleware intricacies.
- **Better suited to others:** 
  - **Claude** should own the **Admin UI (Jinja2/HTML/CSS)**. Claude is generally stronger at frontend aesthetics and ergonomic UI workflows.
  - **Codex** should own the **VCF Ops Client (REST integrations)** since it can deeply leverage the VCF Ops API recon documents and wire-formats to build the data-fetching layers.

## 5. Rough estimate

**Estimate:** ~1.5 weeks for Phase 1.
- Foundation & Middleware: 2-3 days.
- Admin UI & Storage: 2-3 days.
- Read-only tools & VCF Client: 3-4 days.
**Blow-up factors:** If the Streamable HTTP transport in the reference SDK clashes with Starlette middleware, we might lose days debugging ASGI lifecycle events. If DEVEL goes down or is unstable, testing the read-only tools will block the pipeline.
