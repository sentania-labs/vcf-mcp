# 002: MCP framework, the reference SDK's bundled FastMCP on Starlette

- **Status:** accepted
- **Date:** 2026-07-20
- **Assignment:** vcf-ops-mcp round 1, architecture forks 1-6
- **Orchestrator run:** `orchestrator-run-20260720-231633`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker

## Context

Fork 2. The SPEC requires Streamable HTTP with API-key auth, and three
surfaces (MCP, admin UI, health) on one listener. The fork was posed as
FastMCP versus the reference MCP Python SDK.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/round1-architecture` | `85cf71244b042709972e8fce4240b3b916965147` |
| codex-worker | `codex/round1-architecture` | `86b3404056be6f67337294dd47bedb477df6a84b` |
| agy-worker | `agy/round1-architecture` | `68e30bdec4329cdb65af5a278ed3388675ba6046` |

**claude-worker:** `mcp` 1.28.x as one direct dependency, having installed it
in a throwaway venv to check rather than recalling from memory.
**codex-worker:** the official `mcp` package using `mcp.server.fastmcp.FastMCP`
mounted as a Streamable HTTP ASGI app inside one Starlette app.
**agy-worker:** the reference SDK via `mcp.server.sse`, mounted on FastAPI.

## Critique (phase 2, adversarial)

**claude-worker on agy-worker (A1):** the fork as agy framed it is a false
dichotomy, and agy is factually wrong twice. `mcp.server.fastmcp` is bundled
inside the official SDK, so choosing the reference SDK does not mean declining
FastMCP. `mcp.server.sse` is the deprecated HTTP+SSE transport from the
2024-11-05 spec, not Streamable HTTP; verified in `mcp==1.28.1`, where
`mcp/server/` contains `streamable_http.py` and `streamable_http_manager.py`
as separate modules from `sse.py`. agy's single named blow-up risk, the one
thing it flagged as capable of wrecking its estimate, does not exist.

**codex-worker on agy-worker (2):** the claim that FastMCP hides the ASGI app
is factually wrong, since `streamable_http_app()` returns Starlette and
`FastMCP.__init__` accepts a token verifier. FastAPI adds a dependency and an
abstraction without a stated requirement.

**codex-worker on claude-worker (3):** a Starlette request middleware sees MCP
HTTP requests, not individual tool invocations. Streamable HTTP can carry
protocol traffic whose request count does not equal tool-call count, so
middleware alone cannot satisfy "every tool call is audited."

**agy-worker conceded all three points:** "Streamable HTTP is natively
supported via FastMCP. [...] The correct ASGI layer is FastMCP, not low-level
SSE. I proposed using `mcp.server.sse` directly. Codex correctly argues this
adds unnecessary protocol plumbing."

## Orchestrator verification

The dependency-graph dispute was settled by measurement rather than argument.
A clean venv with `mcp==1.28.1` installs: `cryptography` 49.0.0, `starlette`,
`uvicorn`, `httpx`, `httpx-sse`, `pydantic`, `pydantic-settings`, `PyJWT`,
`sse-starlette`. It does **not** install `jinja2`, `fastapi`, or `bcrypt`.

This confirms claude-worker and agy-worker were right that `cryptography` is
transitive and not a new dependency, and codex-worker wrong on that fact. See
003 for why codex-worker was nonetheless right that the credential-store
design needs a record.

## Decision (phase 3, synthesis)

**`mcp` 1.28.x as the single direct MCP dependency**, using the bundled
`mcp.server.fastmcp.FastMCP`, with `streamable_http_app()` mounted inside one
Starlette parent app that also carries `/admin` and `/healthz`. One uvicorn
process, one container.

The fork dissolves rather than resolves: FastMCP and the reference SDK are not
alternatives, because the SDK ships FastMCP. The real fork, as claude-worker
named it, is bundled `mcp.server.fastmcp` versus `mcp.server.lowlevel`, and
nothing in the round argued for the low-level API against a fixed surface.

**Against the separate third-party `fastmcp` package** (at 3.x, having passed
through 1.x and 2.x): for a server whose safety properties are the point,
depend on the implementation maintained in lockstep with the spec by the
people who write the spec. Its extra features (composition, proxying,
generated OpenAPI servers) are surface area this project does not need. The
shared lineage makes migration mostly decorator-compatible, so this is a
reversible decision made in the cheap direction.

**FastAPI is rejected.** agy-worker's rationale for it was the claim that
FastMCP hides the ASGI app, which is false. Starlette is already in the SDK's
dependency graph, and a five-form admin UI does not need FastAPI's routing and
validation layer. Adding it would also be a new dependency requiring
escalation, for no stated requirement.

**Stateless HTTP for v1.** The server stores plans and tasks outside transport
sessions, and v1 excludes sampling and elicitation. Recorded knowingly:
this forgoes `resources/list_changed` and subscriptions, which means a client
cannot be notified when a skill's `current` alias advances (claude-worker's
C7). That is accepted for v1 rather than overlooked, and 005 notes it.

**Auth wiring.** A `TokenVerifier` implementation does the API-key lookup from
003. `AccessToken` carries `client_id` as key ID, `scopes` as
`read_only`/`actions`, and `claims` as the permitted target list. Scope is
enforced twice on purpose: at the verifier, so an unscoped key never receives
an `actions` token, and again inside `apply_action`, so a middleware-chain bug
does not become an action execution.

**Audit is structural, not middleware.** codex-worker's point 3 carries against
claude-worker. Every tool handler routes through one mandatory audited
dispatcher; HTTP middleware carries request identity and correlation only.

**Required before the build round commits to this:** a client smoke test
proving initialize, `tools/list`, a tool call, resources, prompts, bearer
rejection, and reconnect through fleet-caddy. Both claude-worker and
codex-worker flagged VCF Private AI Services compatibility as the largest
external risk that local design cannot settle. codex-worker, asked what it
would do with one hour and one question, chose exactly this.

## Division of labor

| Piece | Assigned to | Why this harness |
| --- | --- | --- |
| ASGI skeleton, Starlette parent, MCP mount, lifespan, `/healthz` | codex-worker | It claimed the transport and policy spine and is strong at tracing framework behavior through source |
| `TokenVerifier`, API-key middleware, scope enforcement at both layers | codex-worker | Same spine; its critique found the audit-boundary defect that shapes this piece |
| Private AI Services and fleet-caddy compatibility smoke test | claude-worker | It already stood up `mcp==1.28.1` and verified module contents empirically rather than from memory |

## Dissent

None standing. agy-worker's FastAPI and `mcp.server.sse` positions lost, and
agy-worker conceded both in its critique rather than dissenting. The
concession is quoted verbatim above.

## Protected paths touched

src/vcf_ops_mcp/

## Sign-offs

    Signed-off-by: claude-worker <claude@team.local> 2026-07-20T23:38:12Z
    Signed-off-by: codex-worker <codex@team.local> 2026-07-20T23:33:21Z
    Signed-off-by: agy-worker <agy@team.local> 2026-07-20T23:34:00Z

Transcribed by the orchestrator from each worker's own signature artifact,
because the records live on a branch the workers do not write to. The
artifacts are authoritative and independently checkable:

| Signer | Signature artifact | Commit |
| --- | --- | --- |
| claude-worker | `.team/signoffs/claude-worker-round1-records.md` | `4cde29b` |
| codex-worker | `.team/signoffs/codex-worker-round1-records.md` | `dd9cf51` |
| agy-worker | `.team/signoffs/agy-worker-round1-records.md` | `9576887` |

Each signer confirmed in its artifact that its own dissent, where it has one,
is quoted accurately and was not softened or truncated.
