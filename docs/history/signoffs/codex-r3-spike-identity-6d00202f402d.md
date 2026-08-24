---
reviewed_branch: codex/r3-spike-identity
reviewed_sha: 6d00202f402d1644e2b19f97e27c8ca884d61180
reviewed_by: claude-worker
authored_by: codex-worker
timestamp: 2026-07-25T20:14:00Z
tests_run: independent reproduction of the spike's own test in a throwaway venv outside the repo (/tmp/spikechk-venv, mcp==1.28.1 + uvicorn + httpx), plus source verification against the unpacked mcp-1.28.1 wheel. No repo test suite exists yet; the diff is docs-only.
result: signed-off
---

# Spike 001, FastMCP identity injection

The verdict PASS is load bearing for the dispatcher contract, so I did not
review this on the document's own account. I reproduced it.

## What I ran

I built a throwaway venv in `/tmp` (nothing added to the repo, no dependency
manifest touched) with `mcp==1.28.1`, and re-implemented the spike's own test:
parent Starlette app, `IdentityMiddleware` writing `request.state.identity` from
`x-api-key`, `streamable_http_app()` mounted at `/parent`, a real uvicorn
listener, two concurrent `ClientSession`s ("alpha" and "beta") doing 40 calls
each with a 25 ms await between two identity reads inside every handler.

My run, `stateless_http=False`:

```json
{
  "concurrent_observations": {"alpha/alpha": 40, "beta/beta": 40},
  "alpha_wrong": [], "beta_wrong": [],
  "mount": {"path": "/parent/mcp", "root_path": "/parent"},
  "same_session_key_change": [
    {"before": "initialize-A", "after": "initialize-A"},
    {"before": "later-B", "after": "later-B"}
  ]
}
```

Re-run with `stateless_http=True`, the mode decision 002 selects for v1:
identical result, 40/40, no mismatches. Every number in the document
reproduced exactly, including the mount `root_path` observation and the
same-session key-change pair.

## Checks that could have falsified the claims

1. **Is the mechanism real, or plausible-sounding?** Verified against the
   unpacked `mcp-1.28.1` wheel, not from memory. `RequestContext.request`
   exists (`mcp/shared/context.py:30`).
   `mcp/server/streamable_http.py` attaches the live Starlette request as
   `ServerMessageMetadata(request_context=request)` (lines 274, 543, 566).
   `mcp/server/lowlevel/server.py:759` copies it into a fresh `RequestContext`
   via `request_ctx.set(...)` with `request=request_data`, and resets the token
   at line 798. `Context.request_context` (`mcp/server/fastmcp/server.py:1154`)
   returns that object. The document's step-by-step internal account is
   accurate, and its warning that `request_ctx` is an implementation detail
   rather than the API to import is correct.
2. **Is the code sample real API, or approximated?** It is real.
   `streamable_http_client(url, http_client=...)` is the current 1.28.1
   signature (`mcp/client/streamable_http.py:601`); `streamablehttp_client` is
   the deprecated alias at line 685. The document did not paste an idealized
   snippet.
3. **Is the conclusion wider than the test?** No. The headline is scoped to
   `mcp==1.28.1` in the first sentence, and the concurrency claim is stated as
   "80 calls across two concurrently active sessions in one process", which is
   exactly what the test does. The 25 ms handler pause is the part that makes
   the isolation claim meaningful rather than incidental, and it is present.
4. **Is the same-session key-change finding supported?** Yes, reproduced. The
   second call on an already-initialized session saw `later-B`, so identity
   tracks the HTTP request and not the MCP session. The document draws the
   correct safety consequence from it: this is safe only because authorization
   runs per request, and a session id must never substitute for
   authentication.
5. **Are the gaps honest?** Yes, and the one that mattered most to me is
   disclosed rather than buried: the author tried 40 concurrent in-flight calls
   inside a single `ClientSession`, hit a 1.28.1 client-side limitation, and
   said so in the Proof section instead of quietly dropping the case. It is
   disclosed in prose rather than repeated in the Gaps list, which is my only
   real nit on this document. The listed gaps (single version, single worker
   process, no proxy/resumability/GET-stream coverage, synthetic header values
   rather than real key lookup) match what was actually not exercised.
6. **Is the "Dispatcher consequence" contract implied by the findings?** Yes,
   for the parts that are claims. Steps 1, 3, and 4 follow directly from
   per-request attachment; step 5 follows from the key-change result. Steps 2
   and 3's "fail closed if absent" are prescriptions rather than findings, but
   they are correctly conservative ones: `RequestContext.request` is typed
   optional in the SDK, so a dispatcher that assumes it is present would be
   wrong, and the document tells the spine to reject a missing value.
   `contracts.py` can be built against this.
7. **Scratch artifacts.** The commit is a single 238-line doc file and nothing
   else. No manifest, no venv, no lockfile, no test script. The author's claim
   that no repository dependency manifest was changed holds. My own venv and
   scratch script live in `/tmp` and are not in any tree.

## Constitution

No em-dashes. No credentials or lab material; all identity values are synthetic
strings. No protected path touched (`docs/spikes/` is not in
`.github/protected-paths.txt`). Commit trailer is
`Co-authored-by: codex-worker <codex@team.local>`, correct.

Signed off.
