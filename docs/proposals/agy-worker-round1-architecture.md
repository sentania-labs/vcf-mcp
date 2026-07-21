# Round 1 Architecture Proposal (agy-worker)

## 1. Approach

### Fork 1: Static vs Dynamic Tools
**Recommendation:** Hybrid approach. Static tools for core reads, dynamic generic pipeline for actions.
**Reasoning:** The `GET /api/actiondefinitions` endpoint returns a very large array of available actions (hundreds of definitions, each with `id`, `displayName`, `actionAdapterKindKey`, `contextResourceKindKey`, etc.). Automatically generating a separate MCP tool for every action would explode the client context window and create an unmanageable tool list.
Instead, we should implement static, named tools for the core reads (`inventory`, `metrics`, `alerts`, `reports`) and a small, static set of generic tools for actions:
- `list_action_definitions(target_id, resource_kind)`: Returns available actions for a given resource kind.
- `get_action_parameters(target_id, action_id, resource_id)`: Fetches parameter schema for the specific action on the resource.
- `plan_action(target_id, action_id, resource_id, parameters)`: Simulates or caches the intent and returns a plan summary and `plan_id`.
- `apply_action(plan_id)`: Executes the plan, returning a `task_id`.
- `poll_action_task(task_id)`: Checks async execution status.

### Fork 2: MCP Framework
**Recommendation:** The reference MCP Python SDK mounted on FastAPI.
**Reasoning:** FastMCP is excellent for prototyping but its abstraction hides the ASGI application. We must run an Admin UI alongside the MCP endpoint on the same port, and we need fine-grained control to inject a custom API-key auth middleware for the Streamable HTTP transport. The reference MCP Python SDK (`mcp.server.sse`) integrates cleanly into a FastAPI application, giving us full control over the ASGI middleware stack (for API keys and session auth) while keeping the image footprint small.

### Fork 3: Credential-store encryption and API-key model
**Recommendation:** SQLite with AES-GCM for credentials; hashed API keys.
**Reasoning:** 
- **Encryption:** A persistent volume will hold an SQLite database and a 256-bit encryption key file (0600 permissions, generated on first boot if absent). Target credentials (passwords or tokens) will be encrypted at rest using AES-GCM (via the `cryptography` library's Fernet or raw AESGCM) before being stored in SQLite. 
- **API Keys:** The Admin UI will mint 32-byte secure random hex strings. The server will only store their SHA-256 hash and associated scope (`read-only` or `actions-capable`) in the database. Clients present the key via the `Authorization: Bearer <key>` header.

### Fork 4: Admin UI Stack
**Recommendation:** Server-rendered minimal UI (FastAPI + Jinja2 + plain CSS).
**Reasoning:** A separate SPA requires a build step in CI, increasing complexity. A server-rendered Jinja2 interface is sufficient for the small scope of target registration, API key minting, and audit log viewing.
For authentication, we will use a bootstrap admin credential (stored as a bcrypt hash) and issue a signed, HttpOnly `session` cookie after a successful POST to `/admin/login`. This is robust, simple, and matches standard Python session-auth patterns.

### Fork 5: Skills Content Model
**Recommendation:** Markdown files exposed as MCP resources, prompts, and tools.
**Reasoning:** Skills will live in a `skills/` directory versioned in this repo.
- For conversational clients, we expose them natively as MCP resources (e.g., `skill://vcfops-api/auth`) and prompts.
- For tool-calling consumers (like Agent Builder), we provide static `list_skills()` and `get_skill(skill_name)` MCP tools that read the markdown files from disk.
Phase 3 knowledge mining will simply commit new markdown files into this directory, and the server will discover them on boot.

### Fork 6: API Version Drift Handling
**Recommendation:** Defensive parsing against live DEVEL responses.
**Reasoning:** The offline 9.1 OpenAPI JSON is an unreliable guide for the live 9.0.2 appliance. We will rely on Pydantic models configured with `extra="ignore"` to tolerate undocumented fields gracefully. During development, we will perform read-only recon against the DEVEL appliance's endpoints to lock down the expected shapes. Any fields present in the 9.1 docs but missing in 9.0.2 will be typed as `Optional`.

## 2. Risks

1. **Simulating plan-then-apply:** The VCF Ops API does not natively support a two-phase "plan" for all actions. For actions that execute immediately, we will have to simulate the plan step by locally caching the requested parameters (the "intent") and returning a `plan_id` without actually calling the remote API. Only upon `apply_action` will the remote mutation occur.
2. **401 Re-authentication:** The `OpsToken` expires. If a 401 occurs mid-stream (e.g., during a long polling operation or report download), the client must cleanly re-authenticate and retry. (The reference `client.py` handles basic 401 retries, but this needs careful testing in the MCP tool context).
3. **LLM Tool Chaining:** The hybrid action approach requires the LLM to successfully chain three or four tools (`list_actions` -> `plan_action` -> `apply_action`). This requires very clear tool descriptions and robust error messages if a step is skipped.
4. **Transport Layer Assumptions:** If "Streamable HTTP" means something other than standard SSE (Server-Sent Events) and requires custom chunked POST responses, the reference MCP SDK might require upstream modifications or a heavy custom transport adapter.

## 3. Division-of-labor claim

I (agy-worker) am best suited to own the **VCF Ops client integration and the read-only MCP tools (inventory, metrics, alerts, reports)**. My Gemini harness excels at parsing complex JSON structures, defensively mapping API drift, and writing robust integration logic. This leaves the FastAPI/SSE server shell, the Admin UI, and the encrypted credential store to Claude or Codex, who may have more boilerplate experience with those specific web layers. (If another resident strongly prefers the VCF client logic, I am happy to pivot to the SQLite/encryption store).

## 4. Rough estimate

**15 to 20 agent hours** for the Phase 1 build.
- Server shell + Admin UI + Auth: 5 hours.
- Credential store + Target registry: 4 hours.
- VCF Ops Client + 401 retry logic: 4 hours.
- Core read-only tools implementation: 5 hours.

**What would blow this up:** If the Streamable HTTP requirement means we cannot use standard SSE and must implement custom chunked HTTP POST responses that the MCP SDK does not natively support, requiring us to fork or heavily wrap the transport layer.
