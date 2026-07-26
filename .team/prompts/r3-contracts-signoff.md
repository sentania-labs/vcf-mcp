# Pre-integration peer review: contracts.py

You are claude-worker. You did NOT author this change. codex-worker did.
Your job is the pre-integration peer sign-off gate, per
`.team/signoffs/README.md`.

## What to review

Commit `d8354377f0f8deef12fc11862f89fdcc056c940c` on branch
`codex/r3-contracts`: "Define shared Phase 1 contracts". It adds
`src/vcf_ops_mcp/contracts.py`, `src/vcf_ops_mcp/__init__.py`, and
`tests/test_contracts.py`. Read it with `git show d8354377`.

This is workplan step 1, the only planned serialization point in the round.
Three slices (codex spine, claude read plane which is YOURS, agy delivery,
agy skills) all build against it. A defect here costs four slices, so review
it as though you are about to build on it, because you are.

`src/vcf_ops_mcp/` is a protected path. Its authorization is
`docs/decisions/009-phase1-build-synthesis.md`, signed by all three doers.

## Confirm or deny these specific claims, by name

Do not "sign off". Confirm or deny each of the following, and say which:

1. **The target-configuration-generation and client-invalidation protocol is
   present and correct.** Record 009 Amendment 2 ruling 2 requires
   `contracts.py` to carry it. You are the one who found it missing; codex
   accepted. Check it is actually there and actually works, not gestured at.
2. **It matches spike 001's stated dispatcher contract**, in that spike's
   "Dispatcher consequence" section (`docs/spikes/`, commit `6d00202f`).
   In particular: identity belongs to the HTTP request, not the MCP session;
   `RequestContext.request` is typed optional so a missing value must fail
   closed; a session id must never substitute for authentication.
3. **The read-only enforcement predicate is 5B**: a capability declared per
   tool, checked against a frozen `MUTATING` allowlist that is EMPTY in
   Phase 1. Not verb-based (VCF Ops reads are POST, a verb gate is
   unbuildable). Confirm the allowlist is genuinely frozen and genuinely
   empty, and that a test-only mutating capability exists per decision 5-sub.
4. **The audit envelope supports decision 7's 7C-with-payload**: a durable
   pre-execution attempt record, a typed `outcome_unknown` terminal state,
   reconciliation, and fail-closed.
5. **The framework-neutral claim holds.** The commit message says the values
   and protocols are framework-neutral. Check nothing imports FastMCP or the
   MCP SDK in a way that pins the spine prematurely.
6. **The tests actually test the invariants they claim to.** Run them.
   Report the command and the real output.
7. **Constitution conformance**: no em-dashes anywhere; no credentials or lab
   material; `Co-authored-by: codex-worker <codex@team.local>` parses as a
   real git trailer (check with
   `git log -1 --format='%(trailers:key=Co-authored-by)' d8354377`).

Withholding your signature is a valid and respected outcome. Two of the last
three rounds had a signer catch a real defect by being asked to confirm named
claims. If something is wrong, say so and do not sign.

## Deliverable

You are on branch `claude/r3-contracts-signoff`, cut from the round branch.
Commit exactly one file:
`.team/signoffs/codex-r3-contracts-d8354377f0f8.md`, with the front matter
that directory's README requires (`reviewed_branch`, `reviewed_sha`,
`reviewed_by: claude-worker`, `authored_by: codex-worker`, `timestamp` from
`date -u`, `tests_run`, `result`).

Use the branch that is already checked out; do not create a differently named
one. Commit with a `Co-authored-by: claude-worker <claude@team.local>`
trailer written as a real trailing line, not a literal `\n` escape.
Never run `git push`.
