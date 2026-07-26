# Slice: policy and persistence spine (codex-worker)

You are codex-worker. Record 009 decision 6-sub assigns you the spine, 4 to 6
dispatch-days. You also authored `contracts.py`, which is already merged.

## Ground truth, read these first

- `docs/decisions/009-phase1-build-synthesis.md` is the authority for this
  round. It is signed by all three doers.
- `docs/proposals/2/SPEC.md` is the consensus build spec.
- `docs/proposals/2/WORKPLAN.md` has your slice and its acceptance criteria.
  Your acceptance criteria are pinned; treat them as the contract.
- `src/vcf_ops_mcp/contracts.py` is the shared spine, authored by codex-worker
  at step 1 and peer-reviewed before it reached your branch. **Build against
  it. Do not edit it.** If you believe it is wrong or missing something, stop
  and say so in your commit message and in a note to the orchestrator rather
  than editing it unilaterally; it is the one file four slices share.
- `docs/spikes/001-fastmcp-identity-injection.md` pins the dispatcher contract.
  Its load-bearing finding: **identity belongs to the HTTP request, not the MCP
  session.** Caching identity on the session silently misattributes audit
  records. `RequestContext.request` is typed optional, so a missing value must
  fail closed. A session id never substitutes for authentication.
- `docs/spikes/002-streamable-http-through-fleet-caddy.md` is BLOCKED
  externally (no per-slot caddy config on docker.int). Do not wait on it and do
  not substitute a local proxy for it.

## Measured facts that overrule plausible reasoning

- **VCF Ops read queries are POST**, not GET, for resource query, stats, and
  alerts. Any verb-based read-only gate is unbuildable. Enforcement is 5B: a
  capability declared per tool, checked against a frozen `MUTATING` allowlist
  that is **empty** in Phase 1.
- The canonical auth header is `Authorization: OpsToken`, measured against
  DEVEL by all three doers. Record 006 selects it.
- The DEVEL service account sees 517 resources across 21 adapter kinds.
- There is **no alert acknowledgement verb** and **no action validation
  endpoint** in this API. Do not build against operations that do not exist.

## Constitution, non-negotiable

- **No em-dashes anywhere.** Not in code, comments, docs, or commit messages.
- **No credentials in the repo, CI, logs, or transcripts.** Lab credentials are
  at `/home/scott/foundry/projects/vcf-ops-mcp/.secrets/vrops-credentials.txt`
  (absolute path; `.secrets/` is gitignored and does not exist in your
  worktree). Read-only recon against DEVEL only. **No mutations against any
  live appliance.** The prod appliance is never touched.
- **No new dependencies.** If you think you need one, escalate rather than
  adding it. Use a JSON-compatible skills index rather than adding PyYAML.
- Python 3.12+.
- Commit with a real `Co-authored-by:` trailer on its own trailing line. Not a
  literal backslash-n escape; that defect shipped once and would have vanished
  at squash merge. Verify with
  `git log -1 --format=%(trailers:key=Co-authored-by)`.
- Use the branch already checked out. Do not create a differently named one.
  Check with `git branch --show-current` before you commit.
- **Never run `git push`.** The orchestrator integrates.

## Scope of this dispatch

Your slice is larger than one dispatch. This dispatch is a **first
increment**, and the slice will be redispatched to continue. So:

- Commit working, tested code incrementally. Do not hold everything for one
  perfect final commit; an uncommitted worktree at cap expiry is lost work.
- Prefer depth on the acceptance criteria over breadth of stubs.
- End with the tests you have written passing, and say in your final commit
  message exactly what is done and what remains, so the next dispatch resumes
  without re-deriving it.

## Your slice

The dispatcher package (**sole ownership**), capability and outbound-contract
enforcement, migrations, the encrypted target repository, the versioned keyring
and rotation state machine, API keys and scope intersection, and the audit
repository.

Your pinned acceptance criteria, from the workplan:

- Dispatcher step ordering exactly as SPEC section 3, with each audit failure
  state (`attempt` write failure, terminal write failure) covered by a test.
- The registration mapping's **required core** is enumerated and its extension
  rule is written down, so a per-family field is provably additive.
- `outcome_unknown` is a distinct terminal state in the response envelope,
  distinguishable by a client from both success and retryable failure, with the
  payload in a subordinate field.
- **Free-space reservation accounting is specified numerically**, not as "a
  conservative threshold". Record 009 Amendment 2 ruling 1 additionally makes
  you owe the accounting *semantics*: terminal row, WAL growth, checkpoint
  headroom, and how concurrent admitted calls consume and release the
  reservation. That was the real gap in your own objection. Derive the number,
  declare it, test it, and put it in the Gate 1 packet.
- The test-only mutating capability runs through the real dispatcher against
  read-only, actions-enabled, and prod fixtures, asserting deny, allow, deny.
- `MUTATING == frozenset()` asserted in the production registry.
- An end-to-end test observes an audit record for every listed tool.

Decision 1's binding rider: audit unavailability does **not** block startup, but
security-relevant admin writes fail closed while audit is degraded. Decision 2:
SQLite, no rotation in Phase 1. Decision 7: 7C-with-payload.

The prod appliance (`vcf-lab-operations.int.sentania.net`) is hard-blocked
from actions structurally, not by convention. A read-only target's
action-execution paths refuse server-side regardless of what any client asks.
