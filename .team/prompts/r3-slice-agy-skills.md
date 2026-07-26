# Slice: skills (agy-worker)

You are agy-worker. Record 009 decision 6-sub assigns you skills, 2
dispatch-days.

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

Catalog load, digest verification, index regeneration check, four render paths,
and the three seed skills.

## The critic's binding ownership conditions

This slice's ownership was the only 2-2 four-ballot split of the round, decided
by the critic seat voting for you against the orchestrator. The orchestrator
adopted the critic's side. The critic attached a rider that is **binding on
this workplan**, and it exists to protect this slice rather than to constrain
it:

- Skills is a **distinct workplan item with distinct review**. It does not ride
  the delivery slice's estimate, finish line, or PR tail.
- It is **explicitly non-blocking relative to the Gate 1 deploy**.
- If capacity fails that test, this piece is **redispatched to another owner**
  rather than silently folded into the delivery PR.

So: keep this branch and its commits separate from your delivery slice. Do not
merge the two, do not let one's tests depend on the other's, and if you are
running short, say so plainly rather than half-landing it inside delivery.

## Content

Skills content is served **two ways**: as MCP resources and prompts for full
clients, and via `list_skills` / `get_skill` tools for tool-calling-only
consumers such as VCF Private AI Services. Both paths ship in Phase 1.

The suite-api auth walkthrough seed content is **authored by claude-worker**
from its measured recon and handed to you as content. That is roughly one day
of content authoring on claude-worker's side and it does not make it a
co-owner. If that content has not arrived yet, build the catalog, digest
verification, index check, and render paths against the other two seed skills
and leave a clearly marked slot for it.

Use a **JSON-compatible skills index**. Do not add PyYAML; that is a new
dependency and new dependencies are an escalation, not a team call.
