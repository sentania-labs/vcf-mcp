---
reviewed_branch: codex/r3-fix-cancel
reviewed_sha: 59f5c2eba7366898ff10ba00e3aedb3498a0b2e5
reviewed_by: claude-worker
authored_by: codex-worker
timestamp: 2026-07-26T02:14:00Z
tests_run: pytest tests/
result: signed-off
---

Reviewed `git diff e73bad5..59f5c2e` in my own worktree at
`.worktrees/vcf-ops-mcp-rv-claude`, read-only against the author's branch. The
fix is sound and the regression test is real. Signing off.

## The regression test fails on unfixed code, verified directly

I did not take the commit message's word for it. I exported the base tree with
`git archive e73bad5` into a scratch directory, dropped the reviewed commit's
`tests/test_dispatcher.py` on top of it, and ran the new test against the base
`src/` via `PYTHONPATH`. It failed, and it failed for the right reason:

    AssertionError: Lists differ: ['attempt'] != ['attempt', 'cancelled']

That failure short-circuits before the reservation assertion, so the audit-row
half of the finding was the only half actually proven. I then patched the
scratch copy of the test to drop the audit assertions and keep only
`reservations.reserved_bytes`, and re-ran against the same unfixed base:

    AssertionError: 32960 != 0

32960 is exactly one `CALL_RESERVATION_BYTES`, so both halves of the finding
are independently reproduced on base: the terminal row is never written and the
lease is never released. The ratcheting claim in the finding is real, not
theoretical. Both assertions pass at 59f5c2e.

## Leak paths traced separately

I traced the lease release and the terminal audit write as two separate
questions, because the fix could have closed one and not the other.

- Normal return, `TimeoutError`, and `Exception`: the terminal write is
  unchanged and the release moved from two open-coded call sites into a single
  `finally`, which is strictly harder to miss than what it replaced.
- `CancelledError`: caught, recorded as `AuditStatus.CANCELLED` with
  `error_code="handler_cancelled"`, lease released in the `finally`, then the
  original exception instance re-raised at the end. The ordering of
  `except Exception` before `except asyncio.CancelledError` is correct on the
  pinned 3.12 (CancelledError is a `BaseException`, so the earlier clause
  cannot shadow it), and the test proves it empirically: the row reads
  `cancelled`, not `error`.
- `CancelledError` is re-raised, and the same object rather than a fresh one.
  Structured concurrency is preserved. I checked specifically that the
  audit-write-failure branch does not swallow it: when
  `append_committed` raises and `cancellation is not None`, the code
  deliberately declines to return the `OUTCOME_UNKNOWN` envelope and falls
  through to re-raise. Returning a value from a cancelled task there would have
  been the worse bug, and the author got it right.

## Double-release and double-write

No double-release. `ReservationLease.release()` guards on `self._released` and
returns early, and the earlier failure path (attempt-write failure at
`core.py:142`) releases and raises before finalization is ever reached. No
double-write: `terminal` has exactly one `append_committed` call site.

## Cancellation arriving during finalization

I probed the case the test does not cover, since it is the realistic
production shape: a second `cancel()` landing while the terminal write is
suspended. I used a fake audit whose terminal write is a real suspension point
and cancelled the dispatch task a second time from inside it. Result: the
terminal row is lost but `reserved_bytes` is 0. The lease survives because
`release()` takes an uncontended `asyncio.Lock`, which has a non-suspending
fast path. So the ratchet, which is the actual harm in the finding, stays
closed even under repeated cancellation. The lost terminal row is the same
degradation the pre-existing error paths already have, and it is covered by the
`AuditRepository` reconciliation contract, which closes attempts lacking a
terminal record as `outcome_unknown` and never infers success.

## The audit invariant and the protected path

A cancelled call gets a terminal row whose status reads `cancelled`, never one
that reads as success: `state` stays `TerminalState.OK` on that path but is
never used, because `_record` is passed `status`, and the function re-raises
rather than returning an envelope. I confirmed that by reading, not by
assuming.

`AuditStatus.CANCELLED` is additive. `AuditStatus` is a `StrEnum` with no
ordinal dependency, there is no `match` or exhaustive dispatch on it anywhere
in `src/`, no concrete `AuditRepository` implementation exists yet so there is
no schema or CHECK constraint to migrate, and no test asserts the enum's
membership set. The live `docs/SPEC.md` does not enumerate audit statuses; the
two files that do (`docs/proposals/2/SPEC.md` and the round-3 phase-1 artifact)
are frozen historical records and correctly left alone.

Both changed files are under `src/vcf_ops_mcp/`, which is protected.
`tools/consensus-check.py` fails on the commit alone, as expected, and passes
against a body naming `docs/decisions/009-phase1-build-synthesis.md`, which is
accepted, principal-approved, signed by all three doers, and names
`src/vcf_ops_mcp/` as its protected path in scope. This is a defect fix inside
that record's scope, not a new architectural decision, so no new record is
needed. The orchestrator owns putting the reference in the round PR body.

No em-dashes in the diff. The `Co-authored-by:` trailer is present and names
Codex.

## Suite

`pytest tests/` in the worktree, which is the literal CI command:
125 passed, 13 skipped, 69 subtests passed. Matches the count the author
reported.

## One non-blocking follow-up, deliberately not a blocker

A handler raising a `BaseException` that is not `CancelledError` still leaks.
I confirmed this against the fixed code with both a custom `BaseException`
subclass and a `KeyboardInterrupt`: rows `['attempt']`, `reserved: 32960` in
each case. Finalization is keyed on `except asyncio.CancelledError` rather than
`except BaseException`, so the gap survives the fix.

I am not withholding sign-off for it. The exploitable ratchet requires a
repeatable non-fatal `BaseException`, and the realistic members of that set,
`KeyboardInterrupt` and `SystemExit`, end the process, which takes the
process-local reservation with it. The gap is also pre-existing rather than
introduced here, and it sits outside the finding this commit was dispatched to
fix. Widening the clause to `except BaseException` with an unconditional
re-raise would close it for a few lines of change and is worth a later slice.
Recording it here so it is not lost.
