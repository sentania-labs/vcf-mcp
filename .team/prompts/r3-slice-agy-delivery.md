# Slice: delivery surfaces (agy-worker)

You are agy-worker. Record 009 decision 6-sub assigns you delivery, 8 to 12
dispatch-days. **This is the largest slice in the plan and Gate 1 rests on it
most directly.**

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

Application composition, MCP binding, the admin UI with record 004's full
hardening list, health and readiness, container packaging, the `ai-log-depot`
CI path, and the first deploy through the docker.int slot.

**Do not defer CI and deploy behind admin and MCP.** That was the original
mitigation and it defers the long pole, which is how a tail becomes the
schedule. Start CI and packaging early in this slice.

Your pinned acceptance criteria, from the workplan:

- **Every record 004 hardening requirement has a test.** There are nine,
  including recent-reauth, which carries its own state and its own tests.
- The auth-source picker is populated from the target's unauthenticated
  `GET /api/auth/sources`, plus a "Local users" entry.
- Security-relevant admin writes fail closed while audit is degraded (the
  decision 1 rider), asserted.
- `/healthz` reports audit writability, readiness, and the unreconciled
  `outcome_unknown` count derived from durable storage.
- Deploy verifies `/healthz` and rolls back to the prior digest on failed
  health **without touching persistent volumes**.

VCF Ops targets are post-deployment configuration entered through the admin UI,
never baked into the image or CI. A newly registered target starts **read-only**
per target. The prod appliance may only ever be registered read-only until
Scott personally flips it.

## Two process notes aimed at this seat specifically

Both are on the record and neither is a slight; they are the two things most
likely to cost this dispatch.

1. **Depth.** Your last two review artifacts were the shallowest of the round,
   including an 8-line sign-off in a 96-second dispatch that confirmed the
   acceptance criteria for this very slice as "unambiguous, directly testable,
   and buildable as written". This dispatch is where that claim gets tested. If
   something in the criteria is not buildable as written, saying so with
   specifics is worth more than confirming it again.
2. **Branch and trailer discipline.** On a prior dispatch you created your own
   branch instead of using the provisioned one and committed to the repo root
   instead of the intended directory, which read exactly like a dead dispatch
   and was not. Run `git branch --show-current` and confirm it is the branch
   named in this prompt before you commit. Your trailer must read exactly
   `Co-authored-by: agy-worker <agy@team.local>`, not `Antigravity`.
