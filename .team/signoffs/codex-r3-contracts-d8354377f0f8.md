---
reviewed_branch: codex/r3-contracts
reviewed_sha: d8354377f0f8deef12fc11862f89fdcc056c940c
reviewed_by: claude-worker
authored_by: codex-worker
timestamp: 2026-07-25T23:14:49Z
tests_run: PYTHONPATH=src python3 -m unittest discover -s tests -v
result: changes-requested
---

Reviewed in `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-codex` at
`d835437`, read-only, no edit made there. The dispatch asked me to confirm or
deny seven named claims rather than to sign off. Five hold. **Claim 2 is
denied** and is the blocker. **Claim 4 is partially denied.** One further gap
and two nits are recorded below the claims.

## Claim 1: target-generation and client-invalidation protocol. CONFIRMED, with a gap

The protocol required by record 009 Amendment 2 ruling 2 is present and it is
mechanism rather than gesture:

- `ConfigurationGeneration`, and `TargetRecord.configuration_generation` as the
  value every consumer snapshots.
- `TargetConfigurationChange` rejects a non-advancing generation in
  `__post_init__`, so a stale or replayed change cannot be constructed at all.
  Tested.
- `TargetRepository.save` takes `expected_generation` and returns the change,
  so the optimistic-concurrency check and the invalidation trigger are the same
  call and cannot drift apart.
- `TargetClientInvalidator.invalidate` documents the barrier precisely: mark
  the `previous_generation` client closed atomically on entry so it accepts no
  new work, DRAIN waits for in-flight work and CANCEL cancels and awaits it,
  the client is then removed, and only a `current_generation` client may be
  lazily created. `InvalidationResult` is the proof the barrier was reached,
  and it rejects DRAIN reporting cancelled requests. Tested.
- The consumer obligation is stated where the three slices will read it:
  snapshot before I/O, compare before retry and before returning, discard on
  mismatch, never retry through a closed client. That is decision 4's
  requirement, carried.

This is the piece I asked for and codex built it properly. The asymmetry that
CANCEL may report drained requests while DRAIN may not report cancelled ones is
correct, not an oversight: work that completed before cancellation landed drained.

**Gap, named but not the blocker: nothing says who chooses DRAIN versus CANCEL.**
Decision 4 supplies exactly one selection rule and it is the rule that makes the
seam a security mechanism rather than tidiness: "an operator who flips
`verify_ssl` from false to true is performing a security action, and an
in-flight request must not silently ignore it." That edit requires CANCEL. As
written, `mode` is a free parameter of the admin write, which is agy-worker's
slice, so agy can pass DRAIN for a TLS tightening and in-flight requests
complete against the old permissive client. A protocol that exists to serialize
three slices should carry the one rule the record already decided. A sentence in
the `TargetClientInvalidator` docstring, or better a helper that derives the
mode from which fields changed, closes it.

## Claim 2: matches spike 001's dispatcher contract. DENIED

Two of the three sub-clauses hold. The third does not, and it inverts the
posture the spike exists to establish.

Holds: identity belongs to the HTTP request. `RequestIdentity` is frozen,
`ToolContext` exposes only `request_context`, and its docstring says
outright that the contract "intentionally has no session identity or cached
identity member". There is no session-id field anywhere in the module, so a
session id cannot substitute for authentication through this contract. That is
spike 001's lifecycle finding, correctly encoded as an absence.

**Does not hold: `RequestContext.request` is not typed optional.** The contract
declares

    class RequestContext(Protocol):
        request: HttpRequest

Spike 001's "Dispatcher consequence" item 3 requires that the dispatcher
"extracts identity only from `ctx.request_context.request.state`, validates its
type, and fails closed if it is absent", and its "Exact mechanism" section says
"the dispatcher must reject a missing value". A value that must be rejected when
missing has to be expressible as missing. This type says it cannot be missing.

I checked the real SDK rather than reasoning from the spike text. In
`mcp==1.28.1` (`/tmp/mcpchk2/lib/python3.12/site-packages/mcp/shared/context.py`,
the environment the spike used):

    @dataclass
    class RequestContext(Generic[SessionT, LifespanContextT, RequestT]):
        ...
        request: RequestT | None = None

It is optional **and defaults to None**. So the contract is not merely stricter
than the spike asked for, it contradicts the object it models. Two consequences,
both landing on four slices:

1. A dispatcher author writing `ctx.request_context.request.state.identity`
   gets no type error and no prompt to branch. When `request` is None the
   result is an `AttributeError` on `NoneType` surfacing as a generic 500 or
   `TerminalState.ERROR`, not a typed fail-closed deny with an audit row saying
   identity was absent. The failure is closed by accident of Python semantics
   rather than by contract, and it is indistinguishable in the audit log from an
   upstream fault.
2. A strict type checker will not accept the SDK's `RequestContext` as
   satisfying this Protocol, because a mutable protocol attribute is invariant
   and `Any | None` is not `HttpRequest`. The contract that is supposed to let
   the spine build against the spike does not typecheck against it.

`RequestState.identity: RequestIdentity` has the same shape of problem and I
consider it part of the same fix. `request.state` is a Starlette `State`, and a
missing attribute raises `AttributeError` at access. If parent middleware did
not run for a path, identity is absent, which is precisely the case the spike
says must fail closed.

**Requested change.** Type both as optional (`request: HttpRequest | None`,
`identity: RequestIdentity | None`) so that "absent" is a state the dispatcher
is forced to handle, and state the extraction obligation in the `ToolContext`
docstring: read only from `request_context.request.state.identity`, deny with a
typed error if `request` is None or `identity` is absent or is not a
`RequestIdentity`, never read a module global, never cache on a session. This
is a small diff and I would sign it immediately.

## Claim 3: read-only predicate is 5B. CONFIRMED

The predicate is capability-based, not verb-based. Every tool declares exactly
one `capability` at registration (`ToolSpec.capability`), the outbound contract
is the separate second layer (`OutboundContract` carries method, path template,
and a frozen `permitted_query_parameters` set, which is decision 5's parameter
allowlist and the thing that catches the silently-ignored-parameter blowup).
`HttpMethod` exists only inside `OutboundContract` and is never consulted as an
authorization predicate anywhere in the module, which is what "the verb carries
no independent weight" has to look like in code.

`MUTATING` is genuinely frozen (a `frozenset`) and genuinely empty
(`frozenset()`), asserted in `test_production_mutating_set_is_empty`, which is
the diff-review tripwire decision 5-sub asked for. `TEST_ONLY_MUTATING_CAPABILITY`
exists as the synthetic capability, is documented as test-scoped, and is
asserted absent from `MUTATING`.

Note on the `Capability` StrEnum: because it is a `StrEnum`, a plain
`"read:inventory"` string and `Capability.READ_INVENTORY` compare and hash
equal, so `CapabilityName = Capability | str` unions cleanly in the frozensets
on `RequestIdentity`. That is correct and I assume deliberate.

## Claim 4: audit envelope supports 7C-with-payload. PARTIALLY DENIED

Three of the four elements hold, cleanly:

- **Durable pre-execution attempt record.** `AuditStatus.ATTEMPT` is a distinct
  status and `AuditRepository.append_committed` names the durability
  requirement in the method itself, so a buffered write cannot satisfy the
  protocol by accident.
- **Typed `outcome_unknown`.** Present in both `TerminalState` and
  `AuditStatus`. `ResponseEnvelope.__post_init__` enforces all three of
  decision 7's rules structurally: the payload rides in the subordinate
  `outcome_unknown_payload` field, `success` must be empty in that state, and
  `retryable=True` raises. The inverse is enforced too, a payload outside the
  state raises. Tested, including both raising cases.
- **Fail-closed.** `AuditRepository.is_writable` gives readiness the signal
  decision 1 and decision 7 need to flip false.

**Missing: the reconciliation surface.** Decision 7 requires that the call be
"surfaced for reconciliation, with a count in `/healthz` and a list in the admin
UI derived from **durable** storage rather than memory", and that on recovery
"`started` rows with no terminal record are closed out as `outcome_unknown`,
never optimistically marked successful". `AuditRepository` exposes exactly
`append_committed` and `is_writable`. There is no method to enumerate unclosed
attempt rows, no method to close them out, and no count.

`correlation_id` makes reconciliation *representable*, which is why this is a
partial denial rather than a flat one, but representable is not the same as
serialized across slices. The audit repository is codex-worker's spine slice and
`/healthz` plus the admin UI list are agy-worker's delivery slice, so this is
the same class of cross-slice seam as ruling 2's invalidation protocol: agy
cannot build the `/healthz` count against this protocol without reaching around
it into codex's SQLite schema. Having put `AuditRepository` into the only
planned serialization point, it should carry the two methods delivery needs.
Suggest `unreconciled_attempt_count()` and something that closes out open
attempts on recovery, or an explicit note that reconciliation is spine-internal
and delivery reads it by some other named route.

## Claim 5: framework-neutral. CONFIRMED

Every import is stdlib: `collections.abc`, `dataclasses`, `datetime`, `enum`,
`typing`. No FastMCP, no `mcp`, no Starlette, no database driver, no HTTP
client. `HttpRequest` and `RequestContext` are structural mirrors of the SDK's
shape rather than imports of it, which is the right way to do this and is what
lets the contract be stated before decision 002's binding is coded. The module
docstring's claim that it performs no I/O is true, there is no executable
statement outside class and constant definitions.

## Claim 6: the tests test what they claim. CONFIRMED

Command run, in codex-worker's worktree, read-only, with
`PYTHONDONTWRITEBYTECODE=1` so I left nothing behind:

    PYTHONPATH=src python3 -m unittest discover -s tests -v

Real output:

    test_configuration_generation_must_advance (test_contracts.ContractTests.test_configuration_generation_must_advance) ... ok
    test_drain_and_cancel_results_are_distinguishable (test_contracts.ContractTests.test_drain_and_cancel_results_are_distinguishable) ... ok
    test_outcome_unknown_is_distinct_and_payload_is_subordinate (test_contracts.ContractTests.test_outcome_unknown_is_distinct_and_payload_is_subordinate) ... ok
    test_production_mutating_set_is_empty (test_contracts.ContractTests.test_production_mutating_set_is_empty) ... ok
    test_registration_required_core_is_explicit (test_contracts.ContractTests.test_registration_required_core_is_explicit) ... ok

    ----------------------------------------------------------------------
    Ran 5 tests in 0.001s

    OK

Five tests, five real invariants, and they are behavioural rather than
decorative: three of the five assert on `ValueError` from `__post_init__`
rather than only on happy-path field values, which is the difference between
testing an invariant and restating a constructor. The two constant tests
(`MUTATING` empty, required core enumerated) are tripwires by design, and
decision 5 explicitly wants the `MUTATING` one to exist so that adding a
mutating capability requires deleting an assertion.

What they do not cover, and I do not think they should at step 1: nothing
exercises the protocols, because protocols have no behaviour until the spine
implements them. The dispatcher tests decision 5-sub requires, the test-only
capability through the **real** dispatcher against read-only, actions-enabled,
and prod fixtures asserting deny/allow/deny, are step 2 spine work and are on
codex's acceptance criteria. Not a defect here.

## Claim 7: constitution conformance. CONFIRMED

- **No em-dashes.** `grep -nP '[\x{2014}\x{2013}]'` across all three added
  files returns nothing (exit 1). Checked en-dashes too, also clean.
- **No credentials or lab material.** No FQDN, hostname, key, token value, or
  lab identifier appears in the diff. `TargetRecord`'s docstring states it
  excludes every credential and token, and the dataclass honours that: no
  password, no token, no keyring field. `ApiKeyScopeRepository.resolve_request_identity`
  takes the presented key as a parameter and documents constant-time digest
  comparison, so the plaintext never lands in a record that could reach a log.
  `AuditRecord` carries `arguments_digest`, not arguments, which is the
  constitution's audit shape.
- **Trailer.** `git log -1 --format='%(trailers:key=Co-authored-by)' d8354377`
  returns `Co-authored-by: codex-worker <codex@team.local>`, so git parses it
  as a real trailer, not as message body text.
- **Protected path.** `src/vcf_ops_mcp/` is authorized by
  `docs/decisions/009-phase1-build-synthesis.md`, signed by all three doers.
  Step 1's scope in `docs/proposals/2/WORKPLAN.md` names `ToolContext`,
  `ToolSpec`, `Capability`, `TargetRecord`, `TargetPosture`, repository
  protocols, and the open versioned registration mapping. All present, plus the
  invalidation protocol added by Amendment 2 ruling 2. Nothing outside that
  scope was committed, and `is_prod` on `TargetRecord` is the field the prod
  hard-block will need.

## Two nits, neither blocking

1. `MUTATING` is annotated `frozenset[Capability]`, but
   `TEST_ONLY_MUTATING_CAPABILITY` is a `str` and the union alias is
   `CapabilityName`. A test-scoped mutating set containing the synthetic
   capability is therefore not type-compatible with anything annotated from
   `MUTATING`'s type, which is awkward given decision 5-sub requires that set
   to run through the **real** dispatcher. Suggest
   `frozenset[CapabilityName]`. The runtime value is unaffected.
2. `ResponseEnvelope` uses `None` to mean "no payload", so a handler whose
   result is literally `None` cannot be wrapped in `outcome_unknown` at all,
   the constructor raises and the dispatcher falls into the generic error arm
   that decision 7 exists to keep it out of. `ToolHandler` returns `JsonObject`
   so this is out of contract today and an empty mapping is fine. A module-level
   sentinel would make it unreachable rather than merely unlikely.

## Summary

The invalidation protocol I asked for in the sign-off round is here and it is
well built, the `outcome_unknown` envelope enforces decision 7 structurally
rather than by convention, and the framework-neutrality and constitution
conformance are clean. I am withholding on one thing: the identity contract
types away the absence that spike 001 says must fail closed, and it does so
against an SDK field that is optional and defaults to None. That is the single
value four slices will read on every tool call, at the only serialization point
in the round, so it is worth one more short commit rather than a comment in the
dispatcher later.

Fix claim 2, and I would like the claim 4 reconciliation methods and the
claim 1 mode-selection rule in the same commit since both are cheap now and are
three-way edits later. Re-review at the new SHA writes a new marker.
