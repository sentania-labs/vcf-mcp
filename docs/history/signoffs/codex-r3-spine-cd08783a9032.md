---
reviewed_branch: codex/r3-spine
reviewed_sha: cd08783a9032e5a40c170cfa387d6ad811a15344
reviewed_by: claude-worker
authored_by: codex-worker
timestamp: 2026-07-26T01:06:40Z
tests_run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
result: signed-off
---

# Peer re-review: policy and persistence spine, second increment

Re-review of `cd08783` against my `changes-requested` marker at `123d9fb`
(`.team/signoffs/codex-r3-spine-123d9fb8bad9.md`, unedited and left standing as
the record of that round). Reviewed read-only in the author's worktree
(`/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-codex`), tracked tree
clean before and after. This marker is committed on `claude/r3-rev-spine` in my
own worktree.

All four blocking items are closed. I signed on evidence from driving the real
dispatcher, not from reading the new tests. One new finding in new code is
carried below as a must-fix, not as a blocker, for the reasons stated there.

## Item 1: denied calls write an audit record. CLOSED.

Probed the same way as last round: eight denial paths driven through
`Dispatcher.dispatch` itself with a real `ToolRegistry` and real
`DispatchDependencies`, counting rows on the audit fake rather than trusting a
test that asserts one row exists. No files written.

```
revoked                    -> DispatchError:key_revoked              | rows: 1 [('denied', 'key_revoked', 'key-1', 'target-1')]
allowlist                  -> DispatchError:target_not_allowed       | rows: 1 [('denied', 'target_not_allowed', 'key-1', 'target-1')]
target_not_found           -> DispatchError:target_not_found         | rows: 1 [('denied', 'target_not_found', 'key-1', 'target-1')]
empty granted scopes       -> DispatchError:scope_denied             | rows: 1 [('denied', 'scope_denied', 'key-1', 'target-1')]
empty global policy        -> DispatchError:scope_denied             | rows: 1 [('denied', 'scope_denied', 'key-1', 'target-1')]
posture read_only          -> DispatchError:target_read_only         | rows: 1 [('denied', 'target_read_only', 'key-1', 'target-1')]
prod forbidden             -> DispatchError:prod_actions_forbidden   | rows: 1 [('denied', 'prod_actions_forbidden', 'key-1', 'target-1')]
audit_space_exhausted      -> DispatchError:audit_space_exhausted    | rows: 1 [('denied', 'audit_space_exhausted', 'key-1', 'target-1')]
no identity                -> IdentityDeny:                          | rows: 0 []
unknown tool               -> KeyError                               | rows: 0 []
allowed read               -> ok                                     | rows: 2 [('attempt', None, 'key-1', 'target-1'), ('ok', None, 'key-1', 'target-1')]
```

Every path that reaches a policy decision now writes exactly one `denied` row
carrying its key id, its target id, and its error code, and then raises. That is
more than I asked for: I named revocation, allowlist, scope, and posture, and
`target_not_found`, `prod_actions_forbidden`, and the new
`audit_space_exhausted` are covered too. `AuditStatus.DENIED` is now produced
rather than merely defined.

The mechanism is a single `_deny` helper (`core.py:202-229`) typed `NoReturn`,
so a deny path cannot fall through to the handler by omission, and the deny
write is awaited before the raise. A failed deny write raises
`audit_denial_write_failed` rather than proceeding, which is the same refuse-on
-audit-failure posture the attempt write already had. That is the right shape:
the audit invariant does not get weaker on the path where the audit log is
already unhappy.

The two remaining unaudited escapes, `IdentityDeny` and the unknown-tool
`KeyError`, are the ones I flagged last round as untyped boundary escapes. They
are now named explicitly in the commit's Remaining list ("unknown-tool,
invalid-identity, and non-JSON argument boundary normalization"), which is what
I asked for in substance: nothing reads as closed that is not. An unregistered
tool is unreachable under the generated-wrapper model and a request with no
identity never got as far as naming a tool, so neither is a live audit hole.

One interaction to record for whoever does that normalization work. `digest` is
now computed at `core.py:72`, above every authorization check rather than below
it. That is required, since the deny row carries the digest, but it means a
non-serializable argument raises `TypeError` ahead of a denial that would
otherwise have been audited:

```
revoked key + non-JSON args  = TypeError rows = 0
```

Nothing regressed (at `123d9fb` that call wrote no row either), and the fix
belongs with the boundary normalization already listed as remaining. Recording
it so the normalization is placed before the digest rather than after it.

## Item 2: the same-session key-change test. CLOSED.

`tests/test_dispatcher.py:test_same_dispatcher_reads_identity_for_each_request`
drives two dispatches through one `Dispatcher` instance with two different
`RequestIdentity` objects and asserts the four resulting rows attribute as
`[key-1, key-1, key-2, key-2]`. That is spike 001 dispatcher consequence 5
exactly: it locks in reauthentication per request and fails loudly if a future
optimization pins identity at initialization. Asserting on the audit rows rather
than on a return value is the stronger form, since it proves attribution follows
identity and not just that the call succeeded.

I did not hold the sign-off on the concurrent two-session half and it is still
absent; the spike proves it at the transport level, and that was my stated
position last round.

## Item 3: tier-1 authorization tests. CLOSED.

SPEC section 11 tier 1 names five dispatcher tests. All five are now covered:

| Tier-1 test | Where |
| --- | --- |
| immediate key revocation | `test_authorization_denials_are_audited_with_attribution`, `key_revoked` subtest |
| empty-scope denial | same, `granted_scopes=frozenset()` subtest |
| target allowlist denial | same, `allowed_targets=frozenset()` subtest |
| global-policy intersection | same, `global_scopes=frozenset()` subtest |
| prod posture constraints | `test_posture_gates_actions` (pre-existing, still passing) |

Folding the four authorization cases into the denial-audit test is a reasonable
call rather than a corner cut: each subtest asserts the error code as well as
the row, so the authorization behavior is pinned independently of the audit
assertion. The `global_scopes=frozenset()` case is the one I most wanted, since
the intersection is easy to accidentally turn into a union in a later refactor
and nothing else in the suite would have caught it.

The subtests raised the suite from 3 subtests to 8.

## Item 4: step 7 named in Remaining. CLOSED.

The commit's Remaining list now opens with "dispatcher-side projection and
result capping seam". `core.py` still returns the handler payload raw at `:195`
while writing `projection_version=spec.projection` onto every row, but that is
now a declared open seam rather than a silent one, which is what I asked for.
Note for the orchestrator's sequencing: the round branch now carries
`src/vcf_ops_mcp/vcf/projection.py` from the merged read plane, so the functions
this seam needs exist and the wiring is a scheduling question rather than a
blocked one.

## Amendment 2 ruling 1: free-space reservation accounting. STARTED, and numeric.

The dispatch asked whether this has begun and whether it is numeric with a
derivation or still prose. It has begun, and it is numeric with a derivation.
Last round it was absent and correctly declared remaining.

`src/vcf_ops_mcp/dispatcher/reservations.py` states named constants and derives
the two thresholds from them rather than asserting a round number:

```
CALL_RESERVATION_BYTES      = 2 records * 4 dirty pages * (4096 + 24) = 32,960
CHECKPOINT_HEADROOM_BYTES   = 1000 frames * (4096 + 24 + 4096)        = 8,216,000
```

Both are pinned by `test_numeric_derivation_is_pinned`, so a change to any input
constant that moves the total is a failing test rather than a silent drift.
Ruling 1's second consequence, the accounting semantics, is answered as well:
what the reservation covers is stated in comments at the constants (attempt plus
terminal row, WAL frame overhead, checkpoint headroom held free even at idle),
and how concurrent calls consume and release it is a lock-serialized
`FreeSpaceReservations` with a `ReservationLease`, tested for concurrent
consumption, exhaustion, headroom refusal, and idempotent release.

Two honest caveats, neither of which makes it prose:

- `DIRTY_PAGES_PER_AUDIT_RECORD = 4` is justified as "the audit table plus three
  indexes", and that schema does not exist yet (migrations are remaining). The
  number is an argued forward assumption, not a measurement. That is exactly the
  falsifiable declared number ruling 1 asked for, and it should be re-derived
  against the real schema when the migration lands.
- `available_bytes` is an injected callable and nothing in `src` supplies a real
  one yet, so admission control is not connected to an actual filesystem. The
  dispatcher-side admission is real (see the `audit_space_exhausted` probe row
  above), the disk-side is not. Consistent with the remaining list.

Deliberately writing one denial row when the audit reserve is exhausted is a
coherent choice, not a contradiction: the checkpoint headroom is held free
precisely so that a small write survives, and refusing silently would be the
worse failure.

## Carried finding, not blocking: a cancelled dispatch leaks its reservation

`core.py` releases the lease on four paths (attempt-write failure, terminal
-write failure, success, error and timeout) but has no `try/finally`, and
`except Exception` does not catch `CancelledError`. A dispatch cancelled while
the handler is running never releases:

```
reserved while in flight     = 32960
reserved after cancellation  = 32960 (expected 0)
timeout path state           = timeout reserved = 0
```

The deadline-timeout path is fine. Cancellation is not, and client disconnect is
the ordinary way a real HTTP server produces one, so under load the reserve
would ratchet down monotonically until every call is refused with
`audit_space_exhausted`. The fix is a `try/finally` around the region from
`acquire()` to the terminal write.

I am recording this rather than blocking on it for three reasons: it is in code
that is inert at this SHA (`reservations` defaults to `None`, nothing in `src`
constructs a `FreeSpaceReservations`, and no composition root exists to wire
one), it was not among my four blocking items, and it will be revisited anyway
when the real free-space source lands. **It must be fixed before the reservation
is wired to anything**, and the orchestrator should carry it into the next spine
dispatch rather than let it ride on this marker alone.

## Nothing I previously confirmed has regressed

Re-verified against `cd08783` rather than from memory:

- **Step order 1 through 6.** Revocation, allowlist, target existence, scope
  intersection, posture, attempt write, handler. Unchanged apart from each deny
  becoming a `_deny` call. Verified by reading `core.py:69-147` and by the probe
  order above.
- **Attempt is committed before the handler runs.** `core.py:140` still awaits
  `append_committed` to completion before `:155` starts the handler. No
  `create_task`, no `gather`. The in-handler assertion test still passes, and the
  happy-path probe shows `['attempt', 'ok']` in that order.
- **HMAC digest leaks nothing.** `_arguments_digest` is byte-identical to
  `123d9fb`. Same HMAC-SHA256 over canonical JSON, same required `digest_key`
  with no default.
- **Identity is read exactly once, from the contract's location.**
  `git grep extract_request_identity cd08783 -- src` returns `contracts.py:230`
  and `core.py:70` only. No cache, no module global.
- **HTTP method is never an authorization predicate.**
  `git grep 'HttpMethod|\.method|outbound_contract' cd08783 -- src` still returns
  only `contracts.py` and `registry.py`. `dispatcher/core.py` does not appear.
- **Posture gating refuses server-side.** The posture branch still reads only
  `target.posture` and `target.is_prod` off the repository-returned frozen
  `TargetRecord`. No client-supplied field reaches it.
- **The mutation gate is exercised through the real dispatcher.** Unchanged, and
  the new denial subtests use the same injected-`mutating` seam rather than
  touching the production `MUTATING` constant.

## Baseline checks

Suite in the author's worktree, up from 12 passed / 3 subtests at `123d9fb`:

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
...................                                              [100%]
19 passed, 8 subtests passed in 0.41s
```

`git status --short --untracked-files=no` empty before and after. The `__pycache__`
directories present are gitignored (`.gitignore:2`) and predate this session's
runs; `git status --untracked-files=all` shows zero pycache entries.

**No em-dashes or en-dashes.** `git grep -nP '[\x{2014}\x{2013}]' cd08783 -- src tests`
returns nothing (exit 1). The pre-existing en-dash I flagged last round is in a
round-3 ballot under `docs/`, not this author's to fix here, and still stands for
the orchestrator.

**No credential or lab material.** `git diff 123d9fb..cd08783 | grep -nEi
'sentania|int\.net|vcf-lab|password|token|api[_-]?key|secret|10\.[0-9]+\.|192\.168\.'`
returns nothing (exit 1). Fixtures remain `fixture.invalid` and
`b"synthetic-test-digest-key"`.

**Protected path.** The diff is four files, all under
`src/vcf_ops_mcp/dispatcher/` and `tests/`, which decision record 009's slice
table gives codex-worker sole ownership of ("the dispatcher package"). The new
`reservations.py` sits inside that package and implements ruling 1, which the
same record assigns to this slice. `contracts.py` is untouched. Nothing outside
the slice was smuggled in.

**Integration note.** `git merge-tree --write-tree round/2-phase1-build
codex/r3-spine` reports no conflicts. The merged read plane touches
`src/vcf_ops_mcp/vcf/` and shares no file with this diff.

## Verdict

Signed off. The audit hole that made this `changes-requested` is closed at the
mechanism level rather than at the test level, the two regression locks I asked
for are real locks, the honesty of the Remaining list is restored, and the
reservation accounting arrived numeric and derived rather than as an adjective.
One carried must-fix on the cancellation release path, stated above.
