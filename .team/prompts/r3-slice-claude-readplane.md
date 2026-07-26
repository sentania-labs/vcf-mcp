# Slice: VCF read plane (claude-worker)

You are claude-worker. Record 009 decision 6-sub assigns you the read plane,
4 to 6 dispatch-days, plus the cross-cutting live tier.

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

The target client, auth and target-configuration generations, TLS, the typed
error hierarchy, projection and result caps, all Phase 1 read adapters, the
synthetic fixture generator, and the contract tests.

Your pinned acceptance criteria, from the workplan:

- Exactly one token acquisition across N concurrent 401s, asserted.
- No re-auth on 403, asserted.
- A **per-request retry counter** bounds retry at exactly one under mid-session
  credential revocation, asserted. This is decision 4 (4B) and it exists
  because agy-worker found a possible unbounded retry when a freshly acquired
  token also 401s.
- Target edit marks the old client closed, and its drain-or-cancel semantics
  are documented and tested. This is the client half of `contracts.py`'s
  target-configuration-generation and client-invalidation protocol.
- Every adapter declares its `(method, path template, permitted query
  parameter names)` triple and its projection version.
- **Metrics caps refuse rather than truncate**, with the cap named in the
  refusal. The numeric cap is yours to derive, declare, test, and put in the
  Gate 1 packet, per Amendment 2 ruling 1.
- The fixture generator preserves reference equality, rejects unknown schema
  paths, and emits generator version, source API version, and generation date.
  A proof test asserts **no raw capture token reaches output**. A scrubber that
  is 99 percent right is a scrubber that leaks; decision 3 (3B) is whitelist
  based for this reason.
- Contract tests assert shape and monotonic properties, **never exact object
  counts**. The service account's object count has already changed once this
  round (4 to 517) and a count assertion would have broken.

Reports scope: this spec ships **report definitions listing only**. Completed
report listing and download are deferred to Phase 2 and the reduction is an
open question to the principal. Build to definitions-only.

TLS: DEVEL's certificate is self-signed and does not validate against the host
trust store. The honest first registration is per-target verification disabled.
A mounted lab CA bundle is the preferred answer and is the principal's call.
**Fingerprint pinning is not budgeted and is not built.**

Read-only recon against DEVEL is allowed and encouraged to verify endpoint
shapes. Mutating anything on a live appliance is not.
