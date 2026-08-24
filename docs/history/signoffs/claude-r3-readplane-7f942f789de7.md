---
reviewed_branch: claude/r3-readplane
reviewed_sha: 7f942f789de7f97f529ed0363e9df8870388a350
reviewed_by: agy-worker
authored_by: claude-worker
timestamp: 2026-07-26T00:47:22Z
tests_run: PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest -m "not live"
result: signed
---

Baseline checks:
- Tests pass in author's worktree: CONFIRMED. Output: `91 passed, 13 deselected in 1.44s`.
- No em-dashes and no en-dashes anywhere in the diff: CONFIRMED. No matches found for `[\x{2014}\x{2013}]`.
- No credential, token, API key, session material, lab FQDN, hostname, or other lab identifier anywhere in the diff: CONFIRMED.
- Scope honesty: CONFIRMED. The diff stays within the authorized bounds of the Phase 1 build synthesis.

Numbered claims checked:
1. **Exactly one token acquisition across N concurrent 401s**: CONFIRMED. Verified in `tests/test_vcf_client.py` via `test_exactly_one_acquisition_across_concurrent_first_calls` and `test_exactly_one_reacquisition_across_concurrent_401s`.
2. **No re-authentication on 403**: CONFIRMED. Verified in `test_no_reauthentication_on_403`.
3. **A per-request retry counter bounds retry at exactly one under mid-session credential revocation**: CONFIRMED. Verified in `test_retry_is_bounded_at_one_under_revocation` and `test_concurrent_revoked_callers_each_stop_after_one_retry` in `tests/test_vcf_client.py`. Moving auth generation does not loosen the bound.
4. **Every adapter declares its (method, path template, permitted query parameter names) triple and its projection version, and refuses anything outside that declaration before a socket is touched**: CONFIRMED. Verified `ReadContract` definitions in `src/vcf_ops_mcp/vcf/adapters/*.py` and `outbound.py`, and `client.py` uses `check_query` and `check_body` before HTTP fetches.
5. **Metrics caps refuse rather than truncate, derived in caps.py, declared/tested/in Gate 1 packet**: CONFIRMED. Checked `caps.py`, tests in `test_vcf_client.py`, and `docs/read-plane.md` (Gate 1 packet).
6. **The fixture generator is whitelist-based per decision 3B**: CONFIRMED. Verified negative control in `ProofTests.test_the_proof_test_fails_on_an_unscrubbed_document` (`test_vcf_fixture_generator.py`).
7. **Contract tests assert shape and monotonic properties and never exact object counts**: CONFIRMED. Grepped tests for 517, 1216, 879, 142. They only appear in comments or mock fixture string inputs.
8. **The live tier cannot escape read-only or reach prod**: CONFIRMED. Verified `PROD_FQDN` exclusion from `LIVE_HOST_ALLOWLIST` in `tests/live/guard.py`, HTTP request hook logic (`refuse_outside_the_read_set`), and tier 1 `tests/test_live_guard.py`.
9. **Nothing from the live runs was committed**: CONFIRMED. Diff includes no JSON captures, no secrets, no session material.
10. **`contracts.py` was not edited**: CONFIRMED. `git diff 33bca5d..7f942f7 -- src/vcf_ops_mcp/contracts.py` is entirely empty.
