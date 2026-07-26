---
reviewed_branch: codex/r3-contracts
reviewed_sha: 8806063306ad7a0a85f20adf26d4aee0b8f91ed1
reviewed_by: claude-worker
authored_by: codex-worker
timestamp: 2026-07-25T23:44:25Z
tests_run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
result: signed
---

Re-review of `codex/r3-contracts` at `8806063`, in
`/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-codex`, read-only, no
edit made there. My first-round marker at
`.team/signoffs/codex-r3-contracts-d8354377f0f8.md` stands as the record of
that round and is not edited.

The revision is `d835437..8806063`, 73 lines in `contracts.py` and 78 in
`tests/test_contracts.py`. Codex declined nothing; the commit message claims
every requested change was made and I confirm all six items below. The blocker
is closed. **Signed.**

## 1. The blocker, claim 2. CLOSED

All three parts of the requested change are present.

**Types.** `RequestContext.request` is now `HttpRequest | None` and
`RequestState.identity` is `RequestIdentity | None` (`contracts.py:75,85`).

**Checked against the real SDK again, not the spike text.** Same environment as
the first round, `mcp==1.28.1` at
`/tmp/mcpchk2/lib/python3.12/site-packages/mcp/shared/context.py:30`:

    request: RequestT | None = None

The contract now matches the object it models rather than contradicting it, so
both consequences I named are gone: a dispatcher author gets a type error on an
unguarded `.request.state`, and the SDK's `RequestContext` is no longer rejected
as failing to satisfy this Protocol on an invariant mutable attribute.

**Obligation stated.** The `ToolContext` docstring (`contracts.py:90-96`) now
states all four clauses: read only from `request_context.request.state.identity`,
deny with a typed error if `request` is None or identity is absent or is not a
`RequestIdentity`, never a module global, never a session cache. It replaces the
old wording rather than sitting beside it, so there is one instruction, not two.

**Absence is expressible and the deny is typed.** `IdentityDeny`
(`contracts.py:223-227`) carries `error_code = "request_identity_missing_or_invalid"`
and `audit_status = AuditStatus.DENIED`, so the audit row is a denial with its
own code rather than an upstream fault. `extract_request_identity`
(`contracts.py:230-239`) guards both gates: `request is None`, and
`getattr(request.state, "identity", None)` narrowed by `isinstance`. The
`getattr` default matters and is correct: Starlette's `State` raises
`AttributeError` on a missing attribute, so a plain attribute read here would
reproduce the exact failure the fix exists to remove. The `isinstance` gate
means a wrongly-typed value denies rather than flowing on as an identity.

**The test makes it real.** `test_absent_identity_is_an_auditable_typed_deny`
(`tests/test_contracts.py:79-104`) drives both absence paths, `request = None`
and a request whose `state` carries no identity, asserts `IdentityDeny` rather
than `AttributeError`, and asserts the exception's `audit_status.value` is
`"denied"` and its `error_code` is the specific one. It then asserts the
happy path returns the same identity object by identity, so the guard cannot be
satisfied by a function that denies unconditionally.

This is what I said I would sign immediately, and I do.

## 2. Claim 4, reconciliation. CLOSED, via the repository surface

Codex took the first branch rather than declaring reconciliation
spine-internal. `AuditRepository` (`contracts.py:255-273`) now carries the three
methods delivery needs:

- `unreconciled_attempt_count() -> int` for the `/healthz` count.
- `unreconciled_attempts() -> tuple[AuditRecord, ...]` for the admin list.
- `close_unreconciled_attempts(*, recovered_at: datetime) -> int` for recovery.

The class docstring binds the semantics decision 7 requires: counts and
enumeration derived from committed storage rather than memory, and recovery
closes every attempt lacking a terminal record as `outcome_unknown` and "must
never infer a successful outcome". The keyword-only `recovered_at` is the right
shape for a recovery close, since the closing timestamp belongs to the recovery
pass rather than to the original attempt.

This closes the cross-slice seam I named: agy-worker can build the `/healthz`
count and the admin list against the protocol without reaching into codex's
SQLite schema. No test covers these, correctly, because a Protocol has no
behaviour until the spine implements it; the tests decision 7 wants are step 2
work on codex's acceptance criteria.

## 3. Claim 1, DRAIN versus CANCEL. CLOSED, with one residual noted

Codex took the stronger of the two options I offered. `invalidation_mode_for_change`
(`contracts.py:293-300`) derives the mode from the field diff:
`not previous.verify_ssl and current.verify_ssl` yields CANCEL, everything else
DRAIN. Decision 4's one selection rule is now in mechanism, and it is directional
rather than a bare inequality, so loosening TLS drains and only tightening
cancels, which is what the record actually says.

`test_tls_tightening_requires_cancel` (`tests/test_contracts.py:106-141`)
asserts both arms: false-to-true is CANCEL, and an otherwise-identical edit that
leaves `verify_ssl` false is DRAIN. Asserting the negative arm is what stops the
function from being satisfied by `return CANCEL`.

**Residual, not blocking and not worth another round.** `invalidate` still takes
`mode` as a free keyword parameter, and the `TargetClientInvalidator` docstring
does not name `invalidation_mode_for_change` as the required source of it. A
sufficiently determined admin write can still compute a mode by hand. I am
explicitly not holding on this: my first-round request said a helper closes the
gap and I meant it, the helper is the discoverable and tested route, and a
sentence pointing `invalidate` at it is a one-line follow-up that belongs with
agy-worker's admin write rather than in another contracts round.

## 4. Both nits. CLOSED

**Nit 1.** `CapabilityName` is now declared before `MUTATING`, and `MUTATING` is
annotated `frozenset[CapabilityName]` (`contracts.py:36-37`). The runtime value
is still `frozenset()`. A test-scoped mutating set holding
`TEST_ONLY_MUTATING_CAPABILITY` is now type-compatible with anything annotated
from `MUTATING`'s type, which decision 5-sub needs since that set has to run
through the real dispatcher.

**Nit 2.** `NO_PAYLOAD: Final = object()` (`contracts.py:167`) is the sentinel.
Both `success` and `outcome_unknown_payload` default to it, and all three
`__post_init__` comparisons switched from `is not None` / `is None` to
identity comparisons against the sentinel (`contracts.py:182-196`), so a handler
result of literal `None` can now be wrapped in `outcome_unknown` instead of
raising into the generic error arm decision 7 exists to avoid. The existing test
was updated from `assertIsNone(envelope.success)` to
`assertIs(envelope.success, NO_PAYLOAD)`, which is the honest assertion, and a
new case constructs an `outcome_unknown` envelope with an explicit `None`
payload and asserts it survives.

**One forward-looking note for the delivery slice, not a defect here.** Because
`success` now defaults to the sentinel rather than to `None`, an OK envelope
that carries no success payload holds a bare `object()`, which is not
JSON-serializable. Whoever serializes `ResponseEnvelope` must compare
`is NO_PAYLOAD` and omit the field rather than passing it to a JSON encoder. The
sentinel's docstring says what it is, so this is discoverable; I mention it so
the delivery author meets it at design time rather than at a `TypeError`.

## 5. Nothing regressed

Re-checked all five claims I confirmed in round one, against the new head rather
than by memory.

- **Invalidation protocol.** `ConfigurationGeneration`,
  `TargetConfigurationChange.__post_init__`'s monotonicity guard,
  `TargetRepository.save(expected_generation=...)` returning the change,
  `InvalidationResult`'s barrier proof and its DRAIN-cannot-report-cancelled
  rule, and the consumer snapshot-and-compare obligation in the invalidator
  docstring are all untouched. Both their tests still pass.
- **Capability-based 5B enforcement.** The predicate is still the declared
  `ToolSpec.capability`, `HttpMethod` still lives only inside
  `OutboundContract` and is consulted nowhere as an authorization predicate,
  and `permitted_query_parameters` is still the frozen allowlist.
  `test_production_mutating_set_is_empty` still asserts `MUTATING` is empty and
  that the synthetic capability is absent from it; the annotation change did not
  weaken the tripwire.
- **Framework neutrality.** Imports are still stdlib only:
  `collections.abc`, `dataclasses`, `datetime`, `enum`, `typing`. The revision
  added exactly `typing.Final`. No `mcp`, no FastMCP, no Starlette, no driver,
  no HTTP client. The two new module-level functions are pure and perform no
  I/O, so the module docstring's claim still holds.
- **`outcome_unknown` envelope.** Still structurally enforced, and the sentinel
  strengthened it: `success` must be absent in that state, the payload is
  mandatory in it and prohibited outside it, and `retryable=True` raises. All
  three raising cases remain tested.
- **Constitution conformance.** `git grep -nP '[\x{2014}\x{2013}]' 8806063 -- src tests`
  returns nothing (exit 1); em-dashes and en-dashes both clean. No credential,
  FQDN, hostname, token value, or lab identifier in the diff; `TargetRecord`
  still excludes every credential, `AuditRecord` still carries
  `arguments_digest` rather than arguments, and `IdentityDeny` carries an error
  code rather than any presented key material.
  `git log -1 --format='%(trailers:key=Co-authored-by)' 8806063` returns
  `Co-authored-by: codex-worker <codex@team.local>`, so git parses it as a real
  trailer. `src/vcf_ops_mcp/` remains authorized by
  `docs/decisions/009-phase1-build-synthesis.md`, signed by all three doers.

## 6. Scope. CLEAN

`git diff --stat bcc992a..8806063` over the whole branch:

    src/vcf_ops_mcp/__init__.py  |   1 +
    src/vcf_ops_mcp/contracts.py | 353 +++++++++++++++++++++++++++++++++++++++++++
    tests/test_contracts.py      | 189 +++++++++++++++++++++++

Three files, exactly the ones step 1 owns. No spine implementation smuggled in:
the revision's only executable additions are `extract_request_identity` and
`invalidation_mode_for_change`, both pure functions of a handful of lines that
carry a contract rule rather than implement a dispatcher, a repository, or a
client registry. Every repository member added is a Protocol method stub. The
worktree's only untracked material is `.team/markers/` and `scratch/`, neither
staged nor committed here.

## Test run

Command run in codex-worker's worktree, read-only, with
`PYTHONDONTWRITEBYTECODE=1` so nothing was left behind:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v

Real output:

    test_absent_identity_is_an_auditable_typed_deny (test_contracts.ContractTests.test_absent_identity_is_an_auditable_typed_deny) ... ok
    test_configuration_generation_must_advance (test_contracts.ContractTests.test_configuration_generation_must_advance) ... ok
    test_drain_and_cancel_results_are_distinguishable (test_contracts.ContractTests.test_drain_and_cancel_results_are_distinguishable) ... ok
    test_outcome_unknown_is_distinct_and_payload_is_subordinate (test_contracts.ContractTests.test_outcome_unknown_is_distinct_and_payload_is_subordinate) ... ok
    test_production_mutating_set_is_empty (test_contracts.ContractTests.test_production_mutating_set_is_empty) ... ok
    test_registration_required_core_is_explicit (test_contracts.ContractTests.test_registration_required_core_is_explicit) ... ok
    test_tls_tightening_requires_cancel (test_contracts.ContractTests.test_tls_tightening_requires_cancel) ... ok

    ----------------------------------------------------------------------
    Ran 7 tests in 0.001s

    OK

Seven tests, up from five, and both new ones assert on the negative arm as well
as the positive, which is the difference between testing a rule and restating
a function body.

## Summary

The one thing I withheld on is fixed at the root rather than papered over: the
identity contract now types absence as possible, matches the SDK field it
models, states the extraction obligation where four slices will read it, and
proves in a test that absence produces a typed auditable denial instead of an
`AttributeError` on `NoneType`. The two cross-slice seams I flagged are carried
in mechanism rather than in prose, and both nits are closed. Nothing regressed
and nothing outside step 1's scope was committed.

Signed at `8806063306ad7a0a85f20adf26d4aee0b8f91ed1`. This marker stops covering
the branch if that SHA moves.
