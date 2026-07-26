---
source-ref: f136b2aa3a13f3f0637e4d5215b37e18df35fbe8
source-commit: f136b2aa3a13f3f0637e4d5215b37e18df35fbe8
source-blob: 81bc46f1564486fa4042e1aa4ee2dae36b08b229
source-path: phase1-proposal.md
worker: agy-worker
round: round-3
phase: phase1
captured: 2026-07-26
---

# Phase 1 Proposal: vcf-ops-mcp read-only

## Measured findings from DEVEL recon
I queried the DEVEL appliance at `https://vcf-lab-operations-devel.int.sentania.net/suite-api/api/versions` to verify the auth header. I acquired a token using the credentials file and tested both headers.
Both `Authorization: OpsToken <token>` and `Authorization: vRealizeOpsToken <token>` returned an HTTP 200 status code. The assignment's reference to `OpsToken` is valid on this appliance version, but the `client.py` reference uses `vRealizeOpsToken`. For this project, we can use `vRealizeOpsToken` to remain consistent with the provided reference implementation, but either works.

## 1. Approach

**Decomposition and slice boundaries**
We divide the build into these concrete modules:
* `src/vcf_ops_mcp/server.py`: The Starlette ASGI parent app. Mounts the Jinja2 admin UI routes on `/admin`, the health check on `/healthz`, and the `mcp.server.fastmcp.FastMCP` instance for the tool surface.
* `src/vcf_ops_mcp/client.py`: The `VCFOpsClient` abstraction. Holds the base URL, auth source, verify-SSL setting, and token lifecycle logic.
* `src/vcf_ops_mcp/tools/`: Directory containing static tool registrations (e.g. `inventory.py`, `metrics.py`, `alerts.py`, `reports.py`). Every tool handler routes through a central audited dispatcher.
* `src/vcf_ops_mcp/store.py`: The SQLite target registry and credential store. Implements the AES-256-GCM envelope and versioned JSON keyring from record 003.
* `src/vcf_ops_mcp/admin/`: Jinja2 templates and Starlette route handlers for the admin UI (target registration, key minting, audit viewing), secured via scrypt and hardened sessions per record 004.
* `src/vcf_ops_mcp/audit.py`: The synchronous audit log writer.

**Target registry and credential store**
The concrete SQLite schema uses two primary tables:
* `targets`: `target_id` (PK), `hostname`, `auth_source`, `verify_ssl`, `posture` (enum: read-only or actions-enabled).
* `credentials`: `target_id` (FK), `username`, `encrypted_password`, `nonce`, `schema_version`.
If the keyring file is absent, unreadable, or corrupted at startup, the server fails closed immediately during the Starlette lifespan hook. It refuses to bind the port.

**Token lifecycle**
The `VCFOpsClient` maintains a per-target `asyncio.Lock`. When a 401 is encountered, exactly one request acquires the lock and calls `POST /suite-api/api/auth/token/acquire`. Concurrent tool calls await the lock and then retry with the fresh token. The `verify-SSL` setting is passed directly to the `httpx.AsyncClient` instantiation for that specific target, allowing self-signed lab certs without globally disabling verification.

**Read-only enforcement choke point**
The read-only enforcement is structural and located inside `VCFOpsClient._request()`. Before dispatching the HTTP call, the client checks the target's posture. If the posture is read-only (or the target is the hard-blocked prod appliance), the client strictly refuses any HTTP method other than `GET`. This makes the gate unbypassable: even if a developer incorrectly registers an action tool, the underlying HTTP client will block the POST/PUT/DELETE request.

**Test strategy**
To verify against DEVEL while keeping CI hermetic, we will capture sanitized HTTP fixtures. A developer runs a script against DEVEL that makes the required read queries, sanitizes the response payloads (scrubbing hostnames, tokens, and passwords), and saves them as static JSON fixtures. In CI, we use `httpx.MockTransport` to load these fixtures. This proves our JSON parsing against real VCF Ops shapes without bringing secrets into CI.

**Audit log**
The audit log is a JSON Lines (JSONL) file written to a dedicated volume mount. A tool call starts by computing the args digest. Before the tool executes, the dispatcher verifies the volume is writable. When the tool completes, it appends the JSON line. If the volume is full or unwritable, the audit write fails, and the dispatcher explicitly raises an error, failing the tool call to satisfy the invariant that no tool path ships without its audit write. File rotation is handled by the container host (e.g. logrotate on docker.int), not the application.

**CI, container, deploy**
We adopt the `ai-log-depot` standard. A GitHub Actions workflow running on a self-hosted runner logs into `ghcr.io` using its ephemeral `GITHUB_TOKEN`, builds a `python:3.12-slim` based image, and pushes it to `ghcr.io/sentania-labs/vcf-ops-mcp`. A subsequent deploy job uses a repository Actions secret (the slot deploy key) to SCP the compose file and trigger `docker compose pull && docker compose up -d` on the docker.int slot.

## 2. Risks

* **Fixture scrubbing failure:** Hand-scrubbing or script-scrubbing live recon payloads for CI fixtures carries a high risk of leaking a token or password if the script misses a header or a deeply nested JSON field.
* **Audit log synchronous blocking:** Failing a tool call because the audit volume is full means a disk-space issue cascades into a complete MCP outage. This is constitutionally correct but operationally fragile.
* **If I had one hour and one question:** I would ask to test the TokenVerifier and MCP context injection with the actual Claude Code client to ensure our Starlette middleware successfully passes the extracted API key identity down to the FastMCP tool handlers. FastMCP context variables can be tricky to wire from ASGI middleware.

## 3. Division-of-labor claim

I am best suited to own the target registry and credential store (SQLite schema, AES-GCM envelope, startup fail-closed checks). My harness excels at structured data persistence, parsing requirements into concrete database schemas, and strictly adhering to fail-closed security constraints like the keyring absence check. The `VCFOpsClient` concurrency and 401 re-auth should go to codex-worker, as it has strong reasoning for state machines and lock concurrency.

## 4. Rough estimate

I estimate this build round will take approximately 3 to 4 days of calendar time. The core target registry and read-only tools are straightforward (1 to 2 days), but correctly wiring the Starlette parent app with FastMCP, the admin UI, and ensuring the CI/CD pipeline matches the lab standard will consume the remaining time. The largest unknown is the exact shape of the FastMCP context injection.
