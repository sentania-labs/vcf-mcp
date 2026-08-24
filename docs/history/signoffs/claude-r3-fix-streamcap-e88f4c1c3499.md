---
reviewed_branch: claude/r3-fix-streamcap
reviewed_sha: e88f4c1c349951b1e033c2f23497e48d2092258f
reviewed_by: agy-worker
authored_by: claude-worker
timestamp: 2026-07-26T01:50:00Z
tests_run: pip install -e .[test] && pytest tests/
result: signed-off
---

The streaming fix is sound. I verified the following:

1. Peak memory is bounded. Accumulation is safely constrained to the 8 MiB cap plus at most one chunk. On error, the bytearray does not instantiate an `httpx.Response` payload, and the memory is garbage collected.
2. I exported the base commit `e73bad5` to a scratch directory, copied the new test over, and confirmed it correctly fails on the unfixed code (measuring 10 MiB accumulated before error). The test passes on the fixed code.
3. The response stream is always safely closed because `_read_capped` runs under a `try/finally` that closes the stream, ensuring no half-read connections are leaked into the pool on an early abort.
4. The 401 retry path operates safely and identically to before because `_read_capped` consumes small responses (like 401s) and rebuilds a standard buffered response. Retries issue a fresh request properly.
5. Dropping `content-length` and `content-encoding` headers from the rebuilt response is correct. The `aiter_bytes()` method streams decompressed bytes, meaning length and encoding metrics from the wire are no longer valid, and downstream logic strictly expects decoded data.
6. A decompression bomb is safely caught because `aiter_bytes()` yields expanded output chunk by chunk, so the cap bites on the expanded size before full allocation.
7. I ran the full CI pipeline test suite successfully locally using `pip install -e .[test] && pytest tests/`.
