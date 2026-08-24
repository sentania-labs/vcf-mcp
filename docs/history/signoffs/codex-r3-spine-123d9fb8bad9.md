---
reviewed_branch: codex/r3-spine
reviewed_sha: 123d9fb8bad9d23b03c63fbda7f7dbe50ac50c08
reviewed_by: claude-worker
authored_by: codex-worker
timestamp: 2026-07-26T00:48:59Z
tests_run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
result: changes-requested
---

# Peer review: policy and persistence spine, first increment

Reviewed read-only in the author's worktree
(`/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-codex`), which was at
`123d9fb` with a clean tracked tree. The marker is committed on
`claude/r3-rev-spine` in my own worktree.

The code that is here is good. The authorization chain is correctly ordered,
identity is read exactly where the contract says, the attempt-before-handler
ordering is real and tested, and the digest scheme leaks nothing. The reason
this is `changes-requested` rather than `signed-off` is narrower than that: two
things the commit message lists under **Done** are not done, and the gap in each
case is invisible to a later reader.

1. **No denial produces an audit row.** Every deny path raises before the
   attempt write, so a refused tool call leaves no durable trace at all.
   `AuditStatus.DENIED` and `TerminalState.DENIED` exist and are never produced.
2. **The spike's two mandated identity tests are absent**, as are the tier-1
   authorization tests for code paths this commit claims as done.

Details, per numbered claim, below.

## Baseline checks

**Tests pass.** Run in the author's worktree; there is no `tools/run_tests.sh`
in this repo, and no `pyproject.toml`, so the suite runs off `PYTHONPATH=src`:

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
............                                                          [100%]
12 passed, 3 subtests passed in 0.77s
```

`git status --short --untracked-files=no` was empty before and after. No
`__pycache__` was created.

**No em-dashes or en-dashes in the diff.**

```
$ git grep -nP '[\x{2014}\x{2013}]' 123d9fb -- src tests docs
123d9fb:docs/proposals/2/ballots/critic-r3-skills-ownership-vote.md:8: ... 4<en-dash>6 days ...
```

(The offending character in that one line is written as `<en-dash>` above so
this marker does not itself become a hit for the same grep.)

The one hit is a pre-existing en-dash in a round-3 ballot, not in this diff.
This commit touches five files (`src/vcf_ops_mcp/dispatcher/{__init__,core,
errors,registry}.py`, `tests/test_dispatcher.py`) and none of them appears in
that grep. Flagging the ballot for the orchestrator as a separate pre-existing
repo-rule violation; it is not this author's to fix here.

**No credential, token, key, session material, or lab identifier in the diff.**

```
$ git diff 33bca5d..123d9fb | grep -nEi 'sentania|int\.net|vcf-lab|password|token|api[_-]?key|secret|10\.[0-9]+\.|192\.168\.'
(no output, exit 1)
```

Fixtures use `fixture.invalid` as the FQDN and `b"synthetic-test-digest-key"` as
the HMAC key, both obviously synthetic. Correct.

**Protected path.** The diff is confined to `src/vcf_ops_mcp/dispatcher/` and
`tests/`, which record 009 decision 6 and the WORKPLAN's spine slice give
codex-worker sole ownership of. `src/vcf_ops_mcp/contracts.py` is untouched by
this commit, which is the right answer for every slice including this one's own
follow-ups. Nothing outside the slice was smuggled in.

## Claim 1: dispatcher step ordering is exactly SPEC section 3

**DENIED, on steps 7 and 8.** Steps 1 through 6 are exact. I walked SPEC
`docs/proposals/2/SPEC.md:100-111` against `core.py:66-163` step by step:

| SPEC step | Code | Verdict |
| --- | --- | --- |
| 1, resolve key identity | `core.py:67` | present (constant-time comparison lives in `ApiKeyScopeRepository`, correctly declared remaining) |
| 2, revocation, then allowlist, then target existence | `core.py:68`, `:71`, `:73-75` | exact, in that order |
| 3, capability vs granted scopes ∩ global policy, default deny | `core.py:76-83` | exact |
| 4, target posture vs capability | `core.py:84-94` | exact |
| 5, write and commit attempt, refuse on failure | `core.py:99-114` | exact |
| 6, run handler with a deadline | `core.py:122-125` | exact |
| 7, project and cap the result | absent | **missing** |
| 8, terminal record: ok, denied, error, timeout, outcome_unknown | `core.py:135-155` | **`denied` never written** |

**Step 7 is absent.** The handler payload is returned raw at `core.py:158`.
`spec.projection` is carried only as `projection_version` on the audit row
(`core.py:201`), which is exactly the shape that reads as done to a later
reader: the audit log will claim a projection version for a result nothing
projected. I accept that the projection *functions* are the read plane's slice
(WORKPLAN, "projection and result caps", claude-worker), but the ordering step
is dispatcher-owned and the seam it needs is not here. What I would need: either
the projection hook on the dispatcher path, or step 7 named explicitly in the
commit's Remaining list so the seam is not mistaken for closed.

**Step 8's `denied` arm is never reached**, which is claim 1's other half and
the substantive finding of this review. See claim 3's note and the standalone
section below.

**Each audit failure state has a test: CONFIRMED.** Attempt-write failure at
`tests/test_dispatcher.py:122-145`, asserting both `audit_attempt_write_failed`
and that the handler never ran; terminal-write failure at `:147-166`, asserting
`OUTCOME_UNKNOWN`, the payload in the subordinate field, and `retryable=False`.
The `FakeAudit(fail_on_write=N)` construction is a clean way to hit exactly one
of the two writes. Both are real tests of the states the acceptance criterion
names.

### The denial audit gap

No refused call writes anything. I ran this against the real dispatcher in the
author's worktree (no files written):

```
revoked      -> key_revoked                          | audit rows: 0
empty-scope  -> scope_denied                         | audit rows: 0
no-identity  -> IdentityDeny                         | audit rows: 0
non-json args-> TypeError                            | audit rows: 0
unknown tool -> KeyError                             | audit rows: 0
handler error-> error / handler_error                | audit rows: 2 ['attempt', 'error']
```

Three things make this a blocker rather than a note:

- `AGENTS.md:81` is unconditional: "Every tool call is audited. Key identity,
  target, tool name, an args digest, and result status go to a durable audit
  log. No tool path ships without its audit write." A denied call is a tool
  call, and a revoked key hammering a target is precisely the record an
  operator wants.
- SPEC section 3 step 8 enumerates `denied` as a terminal audit status, and
  `contracts.py:161`, `:202`, and `:227` all define it. `IdentityDeny` carries
  `audit_status = AuditStatus.DENIED` and docstrings itself "typed, auditable
  denial". Nothing consumes it. That is the contract you and I agreed to last
  round, unimplemented.
- The commit lists "request-local authorization, posture gating" under **Done**
  and does not list denial auditing under Remaining, so nothing signals the gap.

I do not think this needs a large change: the deny paths need to write a
`DENIED` record (or return a `DENIED` envelope that the caller audits) before
raising. What I would need to see: a denied audit row for at least the
revocation, allowlist, scope, and posture denials, with a test asserting the row
exists and carries the key id and target.

Two smaller ordering notes, neither blocking:

- `registry.get()` at `core.py:66` runs before identity extraction, so an
  unknown tool name raises a bare `KeyError` ahead of any authorization. Under
  the generated-wrapper model an unregistered tool is unreachable, so this is
  not a live oracle, but `KeyError` and `TypeError` (the latter from
  `json.dumps` on non-serializable arguments at `core.py:166`) are the two
  untyped escapes from an otherwise fully typed boundary.
- `except Exception` at `core.py:130` discards the handler's exception entirely,
  so the underlying failure is unrecoverable from the audit row's
  `handler_error`. Fine for now, worth a normalized error code later.

## Claim 2: the identity read obeys the contract

**CONFIRMED for the read. DENIED for the test coverage the spike requires.**

The read is correct. `core.py:67` calls `extract_request_identity(context)` and
nothing else; `contracts.py:230-239` reads only
`context.request_context.request`, raises `IdentityDeny` if `request is None`,
and raises again unless `isinstance(identity, RequestIdentity)`. No module
global, no session cache, no fallback. `git grep` over `src` finds no other
identity read. The extracted object is the same one used for both the
authorization decisions (`core.py:68-83`) and the audit rows
(`core.py:103`, `:139`), which satisfies spike consequence 4: attribution and
policy cannot disagree.

The typed-deny cases are tested at `tests/test_contracts.py:81-96` for
`request is None` and for a state object with no `identity` attribute. The third
case, a `state.identity` holding something that is not a `RequestIdentity`, is
handled by the `isinstance` check but not exercised.

**The same-session key-change case is not tested.** Spike 001's "Dispatcher
consequence" item 5 is explicit: "Tests retain the concurrent two-session race
and the same-session key-change case. The latter locks in reauthentication per
request and prevents a future optimization from pinning identity at
initialization." Neither test exists. `git grep -n 'identity' 123d9fb -- tests`
returns only the two contract cases above and `context_for()` helper uses.

This is the load-bearing one. The current code passes both tests trivially
because it caches nothing, which is exactly why the tests are worth having: they
are regression locks against a future optimization, not proofs about today's
code. At the dispatcher level the same-session case is cheap, two dispatches
through one `Dispatcher` instance with two different `RequestIdentity` objects,
asserting each audit row carries the key id of its own call.

While I am in the neighborhood, SPEC section 11 tier 1 names five more
dispatcher tests that this commit's code paths exist for and its message claims
as done: "immediate key revocation, empty-scope denial, target allowlist denial,
global-policy intersection, prod posture constraints". Only prod posture is
covered (claim 5). I verified by probe that the other four paths work correctly
today. They are untested, so nothing stops them regressing.

## Claim 3: the attempt record is durable before the handler runs

**CONFIRMED, to the limit of what is buildable at this SHA.** `core.py:109`
awaits `audit.append_committed(attempt)` to completion, and only then does
`core.py:122` start the handler. Not concurrent, not fire-and-forget, no
`create_task`, no `gather`. A raised write wraps into
`DispatchError("audit_attempt_write_failed")` at `:110-114` and the handler is
never constructed. `tests/test_dispatcher.py:96-98` asserts from *inside* the
handler that exactly `["attempt"]` is already in the log, which is the right
place to assert it.

The commit half is delegated to `AuditRepository.append_committed`, whose
contract name says committed and whose docstring says counts derive from
committed storage. The SQLite implementation that would make that true is
correctly declared remaining, so I confirm the ordering and the delegation, not
the durability, which is not yet testable.

SPEC section 8's "a writability check is not a write" rule is respected:
`is_writable()` exists on the protocol and the dispatcher never calls it in
place of the write.

## Claim 4: HMAC argument digests leak nothing

**CONFIRMED on leakage. Gap on key rotation.**

No raw argument value can reach a row. `AuditRecord` (`contracts.py:208-220`)
has no field that could hold one; the only argument-derived field is
`arguments_digest`, produced at `core.py:165-176` as
`HMAC-SHA256(digest_key, canonical_json(arguments))`. Canonicalization is
`sort_keys=True`, tight separators, `ensure_ascii=True`, so the digest is
stable across key order and unicode representation.
`tests/test_dispatcher.py:120` asserts the argument value `"VM"` does not appear
in the digest. HMAC rather than bare SHA-256 is what SPEC section 8 requires and
the reason it gives (Phase 1 arguments are low-entropy and offline-enumerable)
is correct.

The key comes from `DispatchDependencies.digest_key: bytes` (`core.py:41`), a
required constructor field with no default, so it cannot be silently absent: a
composition root that forgets it fails at construction. That is the right shape.

The gap is rotation, and it is real. `AuditRecord` carries no digest-key
version, so after a keyring rotation old and new rows are silently
non-comparable with nothing in the data saying why, and an operator correlating
"same arguments" across a rotation boundary gets a wrong answer rather than an
error. SPEC section 8's record-field list has the same omission, so this is a
design gap rather than an implementation deviation from an agreed design, and
the commit does declare "keyring rotation" remaining. Not blocking. I would
raise it as a contracts amendment when the keyring lands, since adding a
`digest_key_version` column later means backfilling rows that cannot be
backfilled.

## Claim 5: decision 5-sub is real, not conventional

**CONFIRMED.** `tests/test_dispatcher.py:168-207` builds the fixture through
`registry_with()` (a real `ToolRegistry`, registered and frozen) and
`make_dispatcher()` (a real `Dispatcher` with real `DispatchDependencies`),
then drives all three fixtures through `Dispatcher.dispatch` itself. There is no
stand-in, no monkeypatch, and no direct call to a private check method. The
mutating set is supplied by injection (`mutating=frozenset({TEST_ONLY_MUTATING_
CAPABILITY})`) rather than by mutating the production constant, which is the
right seam.

The three cases assert exactly deny, allow, deny: read-only raises
`target_read_only`, actions-enabled reaches `TerminalState.OK`, and prod raises
`prod_actions_forbidden`. Note the prod fixture is constructed
`ACTIONS_ENABLED` *and* `is_prod=True`, a state SPEC section 4.1 layer 1 forbids
at rest via a CHECK constraint. Testing the dispatcher against a row the schema
will not permit is the correct paranoia: it proves layer 2 stands alone.

`MUTATING == frozenset()` is asserted at `tests/test_contracts.py:26-27`, plus
`assertNotIn(TEST_ONLY_MUTATING_CAPABILITY, MUTATING)`, so the test-only
capability cannot leak into the production set without failing. That assertion
predates this commit (it came in with `contracts.py`), but it holds at this SHA
and satisfies the criterion.

The remaining half of 5-sub, the end-to-end audit record for every listed tool,
is correctly declared remaining and requires the composition root that does not
exist yet.

## Claim 6: enforcement is capability-based, HTTP method is never an authorization predicate

**CONFIRMED by grep, not by reading the design note.**

```
$ git grep -n 'HttpMethod\|\.method\|outbound_contract' 123d9fb -- src
contracts.py:102:class HttpMethod(StrEnum):
contracts.py:109:    method: HttpMethod
contracts.py:128:    outbound_contract: OutboundContract
contracts.py:143:        "outbound_contract",
registry.py:45:        outbound_contract = registration["outbound_contract"]
registry.py:51:        if not isinstance(outbound_contract, OutboundContract):
registry.py:52:            raise TypeError("outbound_contract must be an OutboundContract")
registry.py:75:            outbound_contract=outbound_contract,
```

`dispatcher/core.py` does not appear in that list at all. The dispatcher never
imports `HttpMethod`, never reads `spec.outbound_contract`, and never branches
on a verb. Every authorization branch keys on `spec.capability` and
`spec.key_scope` against `identity.granted_scopes & global_scopes`, then on
`target.posture` and `target.is_prod`. The registry's only interaction with the
method is a type check that the declaration is an `OutboundContract` at all.

That matches decision 5's ruling that "the verb carries no independent weight
and cannot be the predicate", and it is the right answer for the measured
reason: the read fixture in this very test file declares
`POST /api/resources/query`, so a verb rule would have denied a read on line
one.

## Claim 7: posture gating refuses server-side regardless of the client

**CONFIRMED.** The posture decision at `core.py:84-94` reads exactly two values,
`target.posture` and `target.is_prod`, both from the `TargetRecord` returned by
`TargetRepository.get()` at `:73`. No client-supplied field reaches it. The
`arguments` mapping is passed to the handler and to the digest and is never
consulted by any policy branch.

`target_id` is client-supplied, but it is a lookup key, not a decision input,
and it is checked against `identity.allowed_targets` at `:71` before the lookup,
so a client cannot name a target its key does not hold. `TargetRecord` is a
frozen slots dataclass, so a handler cannot mutate posture on the object it is
handed.

One seam worth naming, not a defect: `DispatchDependencies.mutating` defaults to
the production `MUTATING` but is injectable, so the composition root is
load-bearing for this invariant. That is the same seam the test uses, it is
server-side, and no client can reach it. When the composition root lands I would
like to see it construct `DispatchDependencies` without an explicit `mutating`
argument, so the default is what production gets.

## Claim 8: the Remaining list is honest

**DENIED, on two items, both of which appear under Done.**

Honest, and I checked each:

- **Outbound transport enforcement.** Genuinely absent. The contract is
  declared, type-checked, and stored on the spec, and nothing consumes it. No
  transport exists to be half-enforced. `ToolRegistry.freeze()` only blocks
  further registration; it does not compute SPEC 4.2's frozen union, which is
  consistent with the enforcement being unbuilt.
- **SQLite migrations, encrypted targets, keyring rotation, API keys and scope
  persistence, reconciliation.** All are protocol declarations in
  `contracts.py` with no implementation anywhere in `src`. Nothing reads as
  done.
- **Full listed-tool audit coverage.** Correctly remaining; there is no
  composition root and no `tools/list` binding to cover.

Not honest:

- **Denial auditing** is missing while "request-local authorization, posture
  gating" and "terminal audit handling" are listed Done. Claim 1's section
  covers this.
- **Step 7, projection and capping**, is absent from both the code and the
  Remaining list, while `projection_version` is written onto every audit row.

One more thing a later reader could misread, which I would put in Remaining
rather than treat as a defect: SPEC section 3's central mechanism, "what makes
it mandatory is registration, not convention", is not yet load-bearing. The
registrar that generates wrapper closures, the unexported FastMCP instance, and
the private-tool-manager tripwire do not exist. `ToolRegistry` today is a
validated dictionary. The dispatcher is mandatory only for a caller that chooses
to call it. That is squarely the delivery slice's composition root and not this
commit's job, but "the dispatcher is built" and "the dispatcher is
unavoidable" are different claims and only the first is true at this SHA.

## Claim 9: amendment 2 ruling 1, free-space reservation accounting

**Absent here, and it is next-dispatch work, not a gap in this commit.**

Nothing in the diff addresses the numeric accounting: not the terminal row size,
not WAL growth, not checkpoint headroom, not how concurrent admitted calls
consume and release the reservation. There is no threshold constant anywhere in
`src`, and `AuditRepository` has no reservation method to be half-implemented.
The dispatcher does not call `is_writable()` at all, so no partial admission
control is present that would read as the accounting being started.

The commit declares "audit reservation accounting" under Remaining, which is
accurate, and the WORKPLAN prices the spine at 4 to 6 dispatch-days against a
first increment of 579 lines. Deferring it is reasonable. Recording it here so
it is not lost: this is an acceptance criterion of the spine slice and a named
Gate 1 packet item, it is owed numerically rather than as prose, and it is
owed before Gate 1, not before integration.

## Summary of what I would need to sign

1. Denied calls write an audit record. At minimum revocation, target allowlist,
   scope, and posture denials, with a test asserting the row and its
   attribution. This is the `AGENTS.md` audit invariant and SPEC section 3
   step 8.
2. The same-session key-change test, per spike 001 consequence 5. The
   concurrent two-session case too if it is cheap at the dispatcher level; the
   spike proves it at the transport level already, so I will not hold the
   sign-off on that half.
3. Tier-1 authorization tests for the paths this commit claims done: key
   revocation, empty-scope denial, target allowlist denial, global-policy
   intersection.
4. Step 7 either wired or named in Remaining, so `projection_version` on an
   unprojected result is not mistaken for a closed seam.

Items 1 and 4 are correctness and honesty. Items 2 and 3 are regression locks
on code that is correct today, which is when they are cheapest to add.

The digest scheme, the ordering, the identity read, and the mutation gate are
all right, and the mutation gate in particular is exactly what decision 5-sub
asked for rather than a convenient approximation of it. This is a good first
increment with a hole in its audit coverage.
