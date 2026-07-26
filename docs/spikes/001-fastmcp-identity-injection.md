# Spike 001: FastMCP identity injection

**Verdict: yes.** In `mcp==1.28.1`, a tool handler can reliably read the
identity resolved by middleware on the current HTTP request, including when
`streamable_http_app()` is mounted below a Starlette parent. The mechanism is
the injected `mcp.server.fastmcp.Context`, specifically
`ctx.request_context.request`, which is the `starlette.requests.Request` for
the HTTP request carrying that MCP message. Store the resolved identity on
`request.state` and read it from that request. Do not cache it on the MCP
session.

## Question

An API key arrives in an HTTP header. Middleware in the parent Starlette app
resolves it to an identity. Can a tool handler inside the mounted FastMCP
Streamable HTTP app read the right identity for that request, without
cross-request or cross-session leakage, and what happens over a session's
lifetime?

## Exact mechanism

I tested the reference SDK package resolved as `mcp==1.28.1`, installed in a
throwaway Python 3.12 virtual environment. No repository dependency manifest
was changed.

The public handler API is `mcp.server.fastmcp.Context`. FastMCP injects it when
a tool parameter is annotated as `Context`. Its
`Context.request_context` property returns
`mcp.shared.context.RequestContext`; that object's `request` field is
the `starlette.requests.Request` placed in the Streamable HTTP message
metadata. The handler therefore reads:

```python
from mcp.server.fastmcp import Context

@mcp.tool()
async def observe(ctx: Context) -> str:
    return ctx.request_context.request.state.identity
```

The internal transport path explains why this remains per-request:

1. `mcp.server.streamable_http.StreamableHTTPServerTransport` constructs a
   Starlette `Request` from the current ASGI scope and attaches that request as
   `ServerMessageMetadata.request_context`.
2. `mcp.server.lowlevel.server.Server._handle_request` copies the metadata
   request into a new `RequestContext` and sets that context in
   `mcp.server.lowlevel.server.request_ctx`, a `contextvars.ContextVar`.
3. The handler's injected `Context` wraps that request context. The low-level
   server resets its context-variable token after the handler finishes.

`request_ctx` is an implementation detail, not the API the dispatcher should
import. The supported path for product code is the injected
`mcp.server.fastmcp.Context` and its `request_context.request`. FastMCP does
not invent or resolve an identity itself in this arrangement. Parent
middleware must put the resolved, immutable identity on the request state,
and the dispatcher must reject a missing value.

## Proof

The throwaway server used the decided topology: one parent Starlette app,
middleware on that parent, and a mounted `streamable_http_app()`. It ran a
real uvicorn listener rather than an in-process ASGI shortcut. This is the
material part of the proof:

```python
import asyncio

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import Context, FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Mount

class IdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.identity = request.headers.get("x-api-key", "missing")
        return await call_next(request)

mcp = FastMCP("identity-spike", json_response=True, stateless_http=False)

@mcp.tool()
async def observe(delay_ms: int, ctx: Context) -> dict[str, str]:
    before = ctx.request_context.request.state.identity
    await asyncio.sleep(delay_ms / 1000)
    after = ctx.request_context.request.state.identity
    return {
        "before": before,
        "after": after,
        "path": ctx.request_context.request.scope["path"],
        "root_path": ctx.request_context.request.scope["root_path"],
    }

mcp_app = mcp.streamable_http_app()
app = Starlette(
    routes=[Mount("/parent", app=mcp_app)],
    lifespan=mcp_app.router.lifespan_context,
)
app.add_middleware(IdentityMiddleware)

async def one_session(url: str, key: str) -> list[dict[str, str]]:
    async with httpx.AsyncClient(headers={"x-api-key": key}) as client:
        async with streamable_http_client(url, http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                observations = []
                for _ in range(40):
                    result = await session.call_tool(
                        "observe", {"delay_ms": 25}
                    )
                    observations.append(result.structuredContent)
                return observations

alpha, beta = await asyncio.gather(
    one_session(url, "alpha"),
    one_session(url, "beta"),
)
```

The two sessions began together. Each performed 40 calls, and every handler
paused for 25 ms between two identity reads. That forced the two identities to
remain live in overlapping handler tasks and repeatedly yielded control at the
point where a process-global or improperly shared value would be overwritten.
Observed:

```json
{
  "concurrent_observations": {
    "alpha/alpha": 40,
    "beta/beta": 40
  },
  "alpha_wrong": [],
  "beta_wrong": []
}
```

This proves per-request correctness for 80 calls across two concurrently active
sessions in one process. It is also consistent with the SDK source: each
handler task receives its own context-variable context, and each request
context contains its own Starlette `Request`.

I initially attempted 40 concurrent calls inside each individual
`ClientSession`. The 1.28.1 Python client did not reliably support that use:
responses and automatic `tools/list` requests interfered after the session
stream closed. That client-side behavior is not needed for this question, so
the retained test uses two concurrent sessions and sequential calls within
each session. The 25 ms handler pause makes every alpha call overlap a beta
call.

## Streamable HTTP session lifecycle

The identity belongs to each HTTP request, not to initialization or to the
Streamable HTTP session. I initialized one session with `x-api-key:
initialize-A`, made a tool call, changed the same HTTP client's default header
to `x-api-key: later-B`, and made a second tool call on the same MCP session.
Observed:

```json
[
  {"before": "initialize-A", "after": "initialize-A"},
  {"before": "later-B", "after": "later-B"}
]
```

Thus, later requests in an existing session pass through the parent middleware
again and the tool sees the identity resolved for the request carrying that
tool call. It does not retain the initialize identity. This is the safe
behavior only if authorization runs on every request. A session identifier
must never substitute for API-key authentication or identity resolution.

Decision 002 selects `stateless_http=True` for v1. That removes the persistent
transport session but does not change the mechanism: every tool call still
has a current HTTP `Request`. I ran the same 80-call test in that mode and
again observed 40 `alpha/alpha`, 40 `beta/beta`, and no mismatches. I used
`stateless_http=False` for the lifecycle proof because it exercises the harder
session-retention case the spike asks about.

## Effect of mounting

Mounting did not break request state or identity. For a request sent to
`/parent/mcp`, the handler observed:

```json
{
  "path": "/parent/mcp",
  "root_path": "/parent",
  "before": "alpha",
  "after": "alpha"
}
```

Starlette set `root_path` for the mount, while the request state created by
parent middleware remained available on the request FastMCP delivered to the
handler. The parent must adopt the mounted app's lifespan with
`lifespan=mcp_app.router.lifespan_context`; mounting alone does not run a child
Starlette lifespan.

## Dispatcher consequence

The spine slice can build against this contract:

1. Parent ASGI middleware authenticates every MCP HTTP request, resolves the
   API key to an immutable request-identity object, and assigns it to a
   dedicated `request.state` attribute before entering the mount.
2. Every tool handler accepts an injected
   `mcp.server.fastmcp.Context` and immediately routes through the mandatory
   dispatcher.
3. The dispatcher extracts identity only from
   `ctx.request_context.request.state`, validates its type, and fails closed if
   it is absent. It never reads a module global and never caches identity on a
   Streamable HTTP session.
4. Audit and authorization use that same extracted object, so attribution and
   policy evaluation cannot disagree about which request identity applied.
5. Tests retain the concurrent two-session race and the same-session key-change
   case. The latter locks in reauthentication per request and prevents a future
   optimization from pinning identity at initialization.

The SDK's separate bearer-auth helper,
`mcp.server.auth.middleware.auth_context.get_access_token`, was not the
mechanism tested here. Record 002 may use it for the `TokenVerifier` path, but
the parent-middleware identity needed by the dispatcher is available directly
through the current Starlette request as proven above.

## Gaps

- I tested `mcp==1.28.1`, not every future 1.28.x patch or a later minor.
- I tested one uvicorn process and event loop, matching the one-process
  architecture. I did not test multiple worker processes.
- I did not test fleet-caddy, proxy header rewriting, dropped connections,
  resumability with an event store, or long-lived server-to-client GET streams.
  None changes how a POST tool request is attached to its handler context, but
  they need their separately scheduled transport smoke tests.
- The test resolves synthetic header values directly. It proves propagation
  and isolation, not database lookup, hashing, revocation, or the
  `TokenVerifier` implementation.
