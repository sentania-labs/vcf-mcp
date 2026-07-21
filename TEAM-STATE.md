# TEAM-STATE

Orchestrator durable state for vcf-ops-mcp. Read this first on every run,
update it before exiting. This is machinery, not a human changelog.

## Current assignment

**Round:** 3, the Phase 1 build (first real code round)
**Orchestrator run:** `vom-p1-20260721-194336`
**Status:** **in progress, stopped cleanly at the phase-2 boundary.** The SPEC
correction is landed. Phases 1 and 2 are complete and verified. **Phase 3
(ballots + synthesis) is where the next run starts.** No code has been written
yet, by design: this round's phases 1 and 2 produced proposals and critiques
only.

**One new escalation for Scott, and it blocks Gate 1. See "Escalations".**

Round 1 and round 2 are complete and their history is preserved further down
this file, from "Continuation scope, given by Scott" onward. Read the round-3
sections first; the older sections are context, not current state.

### Round mechanics for round 3

- **Round branch:** `round/2-phase1-build`. **LOCAL ONLY**, per the brief. Not
  pushed. No PR open yet.
- **Artifact branch:** `p1-proposals`, holding all three proposals and all
  three critiques, tagged `artifacts/r3-p1-proposals-critiques` so nothing is
  orphaned before the eventual squash merge.
- **Worktrees:** reused at
  `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-<doer>` (the `r1` in
  the path is now just a stale name, the worktrees are generic).
- **Lane: full protocol.** Decomposition and design across the protected path
  `src/vcf_ops_mcp/`, with several genuinely open forks. Not fast-lane
  eligible. The SPEC amendment inside it was triaged separately as fast lane.

### Phase log, round 3

| Phase | Status | Notes |
| --- | --- | --- |
| triage | done | full protocol; SPEC amendment split off as fast lane |
| SPEC amendment (fast lane) | **done** | record 008, codex authored, agy signed off, integrated |
| 1 blind proposal | **done** | three proposals, blindness verified by history walk |
| 2 adversarial critique | **done** | genuinely adversarial, real concessions |
| 3 ballots + synthesis | **not started** | **next run starts here** |
| implementation | not started | |

### Artifact SHAs, round 3

| Doer | Proposal | Critique |
| --- | --- | --- |
| claude-worker | `bfc23827ee5fa47e169a7c0059414c2688d25060` | `48b68d0746779955358953103e6838c56f5ae174` |
| codex-worker | `ae239552ae857294c01adcb4901fc943614ebb20` | `63b3f4b1d818147caa555f87fe3d61d88ae870fd` |
| agy-worker | `f136b2aa3a13f3f0637e4d5215b37e18df35fbe8` | `4fd8004bb909eb841a1d4e57bcae5bb0c884e366` |

All six are reachable from `p1-proposals` and from the tag
`artifacts/r3-p1-proposals-critiques`. **Tag before deleting any branch**, per
the round-1 lesson below.

Proposal artifacts: `docs/proposals/p1-build-claude.md`,
`codex-worker-phase1-build.md`, `agy-worker-phase1-build.md`.
Critiques: `p2-critique-claude.md`, `codex-worker-phase2-critique.md`,
`agy-worker-phase1-critique.md`.

## What round 3 has established so far

These are inputs to the synthesis the next run owns, not decisions. Nothing
below has been balloted.

### Measured, three-way independent convergence: the auth header

The assignment said `Authorization: OpsToken`; the delivered credentials file's
own comment said `vRealizeOpsToken`. All three doers measured DEVEL
independently and converged: **both forms return 200, and `OpsToken` is the
canonical 9.x form.** An arbitrary scheme is rejected, so this is a real
allow-list of two and not an unauthenticated endpoint. Record 006 already
selects `OpsToken`.

agy-worker reasoned toward `vRealizeOpsToken` for consistency with
vcf-content-factory's reference `client.py`. That narrow question is still
live for the synthesis; the underlying fact is not.

The discrepancy was put to the workers as a thing to **measure rather than
resolve by picking the more authoritative-looking source**, explicitly because
round 2 nearly shipped on API operations that do not exist. It worked.

### Measured: VCF Ops read queries are POST, which breaks verb-based gating

claude-worker measured that three of the four core read families (resource
query, stats, alerts) are **HTTP POST**, not GET.

This matters because two proposals independently put the read-only choke point
in the HTTP client as "refuse any method except GET". That predicate is
**factually unbuildable against this API**: it would hard-block exactly the
read traffic Phase 1 exists to serve.

Both authors conceded in the critique round. agy-worker's concession, verbatim,
is worth keeping because it is a clean reversal on measurement:

> I was wrong about verb-based read-only enforcement: In my own proposal, I
> proposed restricting the client to `GET` only if the posture is read-only.
> Claude's measured finding that VCF read queries require `POST` completely
> invalidates my approach. A verb-based gate is unbuildable. I concede to
> Claude's capability-registry approach for read-only enforcement.

The emerging (unballoted) alternative is a **capability registry** checked in
the dispatcher: tools declare a capability, posture is checked against a
`MUTATING` capability set that is empty in Phase 1. The synthesis should test
whether that is genuinely structural or merely conventional.

### Converging, unballoted: decomposition

agy-worker and (per its critique) claude-worker both moved toward
codex-worker's `contracts.py` interface spine, on the argument that defining
`ToolContext` and repository protocols first lets three doers build in parallel
instead of serializing behind a central `dispatch.py`. Two independent moves
toward a third worker's design is a strong signal, but it is still a signal and
not a verdict. **Ballot it.**

### Live, genuinely contested going into synthesis

1. **Audit-write failure semantics.** The constitution says no tool path ships
   without its audit write. claude-worker would refuse to boot on an unwritable
   audit volume. agy-worker argues that takes the admin UI down with it, and
   the admin UI is what an operator needs to diagnose the failure and read the
   audit log. Its position: block tool execution, do not block process startup.
   This is the sharpest disagreement in the round and it is a real one.
2. **Audit storage.** NDJSON append-only, host-rotated, versus codex-worker's
   SQLite with monthly archive rotation. agy-worker attacked the SQLite backup
   path for locking contention on the hot path of every tool call.
3. **Fixture scrubbing.** Every proposal that captures live fixtures has a
   scrubbing problem, and a scrubber that is 99 percent right is a scrubber
   that leaks. Whitelist versus blacklist, and fixture staleness, are both open.
4. **Token single-flight retry bound.** agy-worker found a possible unbounded
   retry when a freshly acquired token also 401s (credentials revoked
   mid-session). Whether the generation-counter designs actually bound the
   retry per request is unresolved.

## Escalations to Scott, current

### NEW and blocking Gate 1: the DEVEL service account sees only 4 objects

**Found by claude-worker during phase-1 recon; independently verified by the
orchestrator before recording it here.**

The delivered read-only `vcf-ops-mcp` account authenticates fine against DEVEL
and can enumerate **21 adapter kinds**, but
`GET /suite-api/api/resources` returns `totalCount: 4`. Its role scope is
restricted to a small object set rather than all objects.

Why this is Scott's call and not the team's: **Gate 1 is defined as Scott
connecting Claude Code with a minted read-only key and running read queries
against DEVEL.** Against a 4-object inventory that gate passes while
demonstrating almost nothing, and it fails in a way that looks like a bug in
this server rather than a permissions scope in the appliance. The team can
build the whole of Phase 1 without this being fixed; the gate is what breaks.

The remedy is a lab-admin change to widen the account's role scope (the
critique names `allowAllObjects`). **The orchestrator did not file that request
itself**, because widening a lab service account's visibility changes its blast
radius on both appliances and that is a principal decision, not a team one.

**Does not block starting the build. Does block Gate 1 being meaningful.**

### Closed 2026-07-21 by this run

- **Escalation 6, `docs/SPEC.md` 4.1 contract error: CLOSED.** Scott ruled
  option 3, drop the alert mutation requirement; alerts are read-only in the
  MVP. Recorded as `docs/decisions/008-alerts-read-only-in-mvp.md`, a
  **directive-authority** record (no worker sign-offs, per
  `docs/decisions/README.md`, because the team deliberately escalated the
  remedy rather than proposing it). SPEC amended by codex-worker at `a222120`,
  peer-reviewed and signed off by agy-worker at `148d80c`, integrated at
  `0481ae7` without rebase so the signed SHA is preserved.
- **Escalation 5, DEVEL read-only service account: CLOSED, it landed.**
  Verified present at `.secrets/vrops-credentials.txt` (mode 0600, gitignored),
  created 2026-07-20 by lab-admin under cross-workspace request `2686d705`,
  role `ReadOnly` on both DEVEL and PROD. Superseded in practice by the new
  escalation above: the account exists and authenticates, but its object scope
  is too narrow for Gate 1.

## Next run starts here

1. **Phase 3: ballots and synthesis.** Read the three proposals and three
   critiques on `p1-proposals`. The four contested questions are listed under
   "Live, genuinely contested" above. Collect **four ballots** on each (yours
   plus all three doers). Per `.team/team-config.yaml`, cursor is
   **tiebreaker-only**: invoke it only on a 2-2 split. Record every losing
   objection verbatim.
2. **Write the decision record** as `009-*.md`. 008 is taken by this run.
   Cite the six artifact SHAs from the table above. Protected path
   `src/vcf_ops_mcp/` is in scope, so it needs sign-offs from all three doers.
3. **Then dispatch implementation** by capability. Record 007 carries a
   prospective division of labor, and this round's proposals carry fresh
   division-of-labor claims that partly contradict it (agy-worker claims the
   store and hands the client concurrency to codex-worker). Prefer the fresh
   claims; they were made against the concrete work.
4. **Put the 4-object escalation in front of Scott** before Gate 1 is
   scheduled.
5. **Non-blocking sweep items:** `tools/consensus-check.py:516` still cites
   `001-town-motion.md`, a template leftover, prose only. And codex-worker
   reported a duplicated `logs via VCF Ops).` line in `docs/SPEC.md` section 5
   that it deliberately left alone because record 008 did not authorize that
   correction. That was the right call; it needs its own authorization.
   The `src/core/` and `ARCHITECTURE.md` strings elsewhere in
   `consensus-check.py` are deliberate synthetic fixtures and must **not** be
   "fixed".

## End-of-run sweep, round 3 (mid-round, not end-of-round)

Run at the close of this orchestrator run. The round is **not** closed, so the
normal end-of-round expectation of zero branches does not apply yet. Every
branch below is **retained on purpose** because the round is mid-flight, and
this section is what makes that a deliberate state rather than an abandoned one.

- **Open team PRs: zero.** Correct: no PR opens until the round branch is
  integrated and green.
- **Doer-prefixed branches on `origin`: zero.** Guard run, passed. `origin` has
  `main` only, plus the 16 `artifacts/*` tags from round 1.
- **Round branch on `origin`: absent, and that is correct.** `round/2-phase1-build`
  is local-only until the PR opens, per the brief. Do not push it early.
- **`TEAM-STATE.md` is on `main` (`73b87bf`), ahead of the round branch.** The
  orchestrator has no feature branch, and the next run reads `main` first. This
  means `main` and `round/2-phase1-build` now differ on this file: **merge
  `main` into the round branch before opening the PR**, per the round-2 note
  below.

Local branches retained on purpose:

| Branch | Why retained |
| --- | --- |
| `round/2-phase1-build` | the round's integration branch, mid-round |
| `p1-proposals` | all six phase-1/2 artifacts, tagged `artifacts/r3-p1-proposals-critiques` |
| `claude/p1-build`, `codex/p1-build` | proposal artifact heads cited by the eventual record |
| `agy/phase1-proposal` | **agy's real proposal head** (`f136b2a`); it ignored the provisioned branch name |
| `agy/p1-build` | **empty, unused.** The branch provisioned for agy that it did not use. Safe to delete; kept this run only so the next run sees why the name appears in the marker |
| `claude/p1-critique`, `codex/p1-critique`, `agy/p1-critique` | critique artifact heads |
| `codex/spec-alerts-read-only`, `agy/spec-review` | the SPEC fast-lane author and sign-off heads, already merged into the round branch at `0481ae7`; safe to delete once the round PR merges |

## Round 1 and round 2 history, below this line

Everything from here down is the completed round-1 and round-2 record, kept for
context. It is not current state.

### Round 1 status, as closed

PR #1 merged as `76c3357`. All five of Scott's resolutions folded into the
records, all three external Codex findings addressed, round and doer branches
swept, `.review-passed` written.

### Continuation scope, given by Scott 2026-07-21

Scott resolved all five round-1 escalations. Full text of the resolutions is
the run's prompt; the substance is folded into records 001 and 003 by this
run. Summary of the rulings:

1. Action authorization is **fine-grained and default-deny**: per-key
   action-class allow-list intersected with a global policy; a newly minted
   key can do nothing until scopes are explicitly granted.
2. **Grantable scopes derive from implemented capabilities**, read or write.
   A scope is assignable only if the server implements the matching
   capability, so there are no phantom grants. This sharpens the earlier
   "no action keys before Gate 2" recommendation into one general rule.
3. **Keyring co-location: Option A ratified**, residual risk accepted for MVP,
   with a deferral ticket. The deferral rationale must be recorded accurately:
   runtime key injection does not remove the key from the host, it only
   relocates it. The genuine win is getting the key off the same volume as the
   ciphertext. Full host-root compromise is unbeatable at this layer. The
   correct long-term answer is an external secrets broker / KMS, not "inject
   the key".
4. **`jinja2` approved.** Closed.
5. **DEVEL read-only service account: in flight**, provisioned via lab-admin.
   Confirm it landed before Phase 1 recon depends on it.

### External Codex findings on PR #1 (one round, no re-review loop)

| # | Finding | Lane |
| --- | --- | --- |
| 1 | 001: revalidate the action against VCF Ops immediately before applying | orchestrator record edit |
| 2 | 001: route alert-acknowledgements and report-runs through plan-then-apply | **full protocol** |
| 3 | Two sign-off markers missing required fields | fast lane |

### Triage for this run

- **Findings 1 and 3, and resolutions 1-3: not design forks.** Finding 1
  restores a freshness check that codex-worker's accepted critique already
  required and synthesis dropped; restoring converged content is a synthesis
  correction, not a new decision. Resolutions 1-3 are the principal's rulings
  being transcribed. Finding 3 is mechanical front-matter.
- **Finding 2 is a design fork and gets the full protocol.** Codex named two
  materially different approaches (a generalized operation type with a payload
  fingerprint, versus dedicated plan/apply paths per API family), it lands in
  a record governing the protected path `src/vcf_ops_mcp/`, and a reasonable
  engineer could pick either. Scoped to that one question rather than
  reopening fork 1.

### Goal statement (verbatim, as given)

> The project was bootstrapped today: constitution (CLAUDE.md), SPEC v1.0
> (docs/SPEC.md), team config, consensus tooling, repo at
> github.com/sentania-labs/vcf-ops-mcp (private, branch+PR strategy).
> Read CLAUDE.md and docs/SPEC.md first; they are the contract. This is
> the project's first round; there is no TEAM-STATE history yet.
>
> Scott's standing rulings, already made (do not re-litigate): name and
> unofficial self-description; deploy to a docker.int slot behind
> fleet-caddy (provisioning request to lab-admin is in flight, so CI's
> deploy job may land in a later round once the handoff facts exist);
> devel appliance first with prod read-only later; Streamable HTTP + API
> keys; VCF credentials are post-deploy admin-UI configuration.
>
> Run the full protocol (blind proposals, critique, ballots, synthesis,
> decision records) on the round's real architecture forks:
>
> 1. Static core MCP tools vs dynamic tool generation from the live
>    `GET /api/actiondefinitions` catalog, or a hybrid. Consider client
>    context cost, tool-count explosion, and what VCF Private AI Services
>    tolerates.
> 2. MCP framework: FastMCP vs the reference MCP Python SDK (or
>    another), for Streamable HTTP + API-key auth middleware.
> 3. Credential-store encryption design (app-managed key file on a
>    volume, algorithm/library, rotation story) and the API-key model
>    (scoping read-only vs actions-capable).
> 4. Admin UI stack (server-rendered minimal vs SPA; files-hosting's
>    session-auth pattern is the lab precedent).
> 5. Skills content model: how skills/ markdown is versioned, exposed as
>    resources/prompts AND as list_skills/get_skill tools, and how the
>    Phase 3 mining round will add to it.
> 6. API version drift handling: the lab appliance is 9.0.2, docs are
>    9.0/9.1. Read-only recon against the DEVEL appliance
>    (vcf-lab-operations-devel.int.sentania.net) is allowed and
>    encouraged to verify endpoint shapes, including its live
>    Swagger/OpenAPI if reachable; VCF-CF's OpenAPI JSONs are the offline
>    reference. NO mutations against any live appliance.
>
> Research inputs (read-only; portable knowledge only, per constitution):
> the knowledge directories and reference material enumerated in SPEC
> section 2, including vcf-content-factory's vcfops-api skill,
> client.py, api-surface recon docs, lessons/rules indexes, and the
> zw008/VMware-AIops repo for pattern comparison. The VCF 9.0 PDF is
> large; sample it purposefully, do not attempt a full read.
>
> Deliverable for this round: decision records under docs/decisions/
> resolving forks 1-6 (or escalating the ones that are genuinely
> Scott's), plus a phase-1 build plan recorded in TEAM-STATE.md, plus an
> amended SPEC only if deliberation exposes a contract error. No
> production code this round; spike/recon scratch under a worktree is
> fine but does not merge.

### Lane

**Full protocol.** Six genuine architecture forks governing a protected path
(`src/vcf_ops_mcp/`). Nothing here was fast-lane eligible. One unrelated
fast-lane item was triaged separately mid-round (see "Fast-lane fix" below).

## Phase log

| Phase | Status | Notes |
| --- | --- | --- |
| triage | done | full protocol |
| 1 blind proposal | **done** | three proposals, cross-doer blindness verified |
| 2 adversarial critique | **done** | three critiques, genuine attacks, real concessions |
| 3 ballots + synthesis | **done** | two questions, four ballots each, both 4-0 |
| records | **done** | 001-006 committed, signed by all three doers |
| integration | **done** | all doer branches merged into `round/1-architecture` |
| PR | **merged** | PR #1 squashed to `76c3357`; external review received and addressed |
| sweep | **done** | round branch and all 14 doer branches deleted; artifacts tagged first, see below |
| external review | **done** | 3 findings, all addressed this run, one review round per convention |
| r2 protocol round | **done** | findings 1+2 ran the full protocol; see below |

## Round mechanics

- **Round branch:** `round/1-architecture`, pushed to origin.
- **PR:** https://github.com/sentania-labs/vcf-ops-mcp/pull/1
- **Worktrees:** `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-<doer>`

### Artifact SHAs (cited by the decision records)

Round 1 (records 001-006):

| Doer | Proposal | Critique | Ballot | Signature + peer review |
| --- | --- | --- | --- | --- |
| claude-worker | `85cf712` | `6eb92bd` | `ab2570c` | `4cde29b` |
| codex-worker | `86b3404` | `5bc71c9` | `da6e6a5` | `dd9cf51` |
| agy-worker | `68e30bd` | `591cfb6` | `0a36659` | `9576887` |

Round 2, the mutation gate (record 007). Artifact branches were **frozen** at
their ballot heads so the peer markers naming those SHAs stay valid; the
signature and peer-review artifacts went on separate `*/r2-signoffs` branches
for the same reason.

| Doer | Proposal | Critique | Ballot | Signature + peer review |
| --- | --- | --- | --- | --- |
| claude-worker | `ce6e6c0` | `eb79162` | `f2669cf` | `a307102` |
| codex-worker | `63567bf` | `9fbed79` | `74a675b` | `10c9282` |
| agy-worker | `a08f6ae` | `afa891f` | `9486d62` | `726daf4` |

Peer review assignment rotated so no resident reviewed its own work:
claude reviewed codex, codex reviewed agy, agy reviewed claude.

### Artifact commits are preserved by tags, and this is load-bearing

**The squash merge broke every SHA citation in the records, and tags are the
fix. Do this on every future round.**

`docs/decisions/README.md` says a proposal is cited by full 40-character SHA so
a reader can check out exactly what a worker proposed before it saw the others.
PR #1 was **squash** merged, so not one artifact commit is an ancestor of
`main`: verified after the merge, `git merge-base --is-ancestor` returns false
for all of them. The artifact *files* survive in `main`'s tree, but every SHA
the records cite would have become unreachable the moment the branches were
deleted, and would eventually be garbage collected. The records would still
have claimed the SHAs were "authoritative and independently checkable" while
being silently false.

Round 1's note said citations "resolve after the doer branches are deleted"
because they were merged into the round branch. That reasoning quietly assumed
the round branch survives. It does not; PR hygiene requires deleting it.

Before deleting any branch, every artifact commit was tagged and the tags were
pushed to `origin`:

- `artifacts/round1-integrated` at `ec76fa9`, the integrated round-branch head
  as merged. This one tag reaches **every** artifact commit cited by records
  001 through 007.
- Per-branch tags for legibility: `artifacts/r1-{claude,codex,agy}`,
  `artifacts/r2-{claude,codex,agy}-gate`,
  `artifacts/r2-{claude,codex,agy}-signoffs`, and the marker-fix and
  consensus-fix branch heads.

16 `artifacts/*` tags are on `origin`. **Do not delete them.** They are the only
thing keeping the decision records' citations honest.

All are merged into `round/1-architecture`, so the records' citations resolve
after the doer branches are deleted. **Do not delete a doer branch before
confirming its commits are reachable from the round branch.**

## What this round decided

Six records under `docs/decisions/`. Read them rather than this summary.

The round turned on measurement. claude-worker and codex-worker independently
ran read-only recon against DEVEL and converged on the same numbers: 142 action
definitions, all type `UPDATE`, **no parameter metadata in the list response**.
That structural fact is why dynamic tool generation is impossible, and it is a
stronger reason than the tool-count argument the assignment anticipated.
agy-worker reasoned from an unmeasured estimate and conceded in full.

Ballots were 4-0 on both contested questions (skills content model, keyring
co-location), so **the critic seat was correctly not invoked**. Per
`.team/team-config.yaml` cursor is tiebreaker-only on a 2-2 split.

## What round 2 decided (record 007)

The mutation gate, resolving both substantive external findings. Read record
`007-mutation-gate-generalization.md` rather than this summary.

**The round's discovery: the VCF Ops API has no alert acknowledgement verb.**
codex-worker and claude-worker found it independently; the orchestrator verified
it before synthesis. `acknowledg` appears **zero times** in the 9.1 OpenAPI, and
the real verb set is suspend, cancel, takeownership, releaseownership,
assignownership. There is also **no action validation endpoint**: the action
surface is exactly four paths. Two of three proposals were built on operations
that do not exist, and claude-worker's phase-1 verb list was wrong in its own
recon, which it disclosed unprompted.

Four contested questions, four ballots each. **No question split 2-2, so the
critic seat was correctly not invoked.** Results: one alert per plan (3-1),
action revalidation as a blocking Phase 2 gate question (4-0), flat optional
scalars for `plan_mutation` (4-0), `report:run` ships shallow (3-1),
`report:publish` deferred (4-0). Dissents from agy-worker (Q1) and codex-worker
(Q4a) are recorded verbatim in 007.

Two workers voted against their own prior positions and said so.

**Two orchestrator-authored rulings**, flagged as such in the record because
they were not balloted: the submitted-bytes ruling (submit stored bytes,
recomputed payload is a comparison input only) and the stale-denial-rate ruling.
All three doers were asked to object and none did.

## Escalations to Scott

### Resolved 2026-07-21, folded into the records

1. **Action authorization granularity** (001). Fine-grained, default-deny.
2. **Grantable scopes** (001, 003). Derived from implemented capabilities, read
   or write, so there are no phantom grants.
3. **Keyring co-location** (003). Option A ratified, residual risk accepted for
   MVP. The deferral points at an external broker/KMS, **not** at runtime key
   injection, which only relocates the key rather than removing it.
4. **`jinja2`** (004). Approved. Closed.

### Open

5. **A DEVEL API service account** (006). **In flight**, not closed. Scott had
   lab-admin provision a read-only `vcf-ops-mcp` account on devel and prod;
   the cross-workspace request is filed. **Confirm the account landed before
   Phase 1 recon depends on it.** Until then recon borrows
   vcf-content-factory's `devel` profile, which is what both rounds used.

6. **NEW: `docs/SPEC.md` 4.1 contains a contract error.** It requires "alerts:
   alerts, symptoms, acknowledge", and the API has no acknowledge verb. This is
   Scott's call, not the team's: SPEC is the design contract and a protected
   path, and the nearest substitute verb is `cancel`, which closes an alert
   outright and is materially wider than what SPEC's wording implies. The team
   did not guess. Three options are laid out in record 007's "Escalated to the
   principal". **Does not block Phase 1**, since no alert verb is grantable in
   MVP.

## Fast-lane fix taken mid-round

`tools/consensus-check.py:572` asserted `src/photoflow/`, a leftover from the
template repo the tooling was copied from, so `--self-test` failed and would
have blocked this round's own PR. Commit `67044f1` had claimed to fix exactly
this and fixed only one of two occurrences. Dispatched to codex-worker
(`a3e1a89`), peer-reviewed by claude-worker (`b2ec104`). Self-test now passes
and the full gate returns exit 0.

**Left for a later sweep, non-blocking:** claude-worker found that the comment
at `tools/consensus-check.py:516` still cites `001-town-motion.md`, another
template leftover. It is prose in a comment with no behavioral effect. The
`src/core/` and `ARCHITECTURE.md` strings elsewhere in that file are deliberate
synthetic fixtures, not leftovers, and must not be "fixed".

## How the three external findings were addressed

| Finding | Lane | Resolution |
| --- | --- | --- |
| 001: revalidate before applying | full protocol, merged with the next | Record 007. Mandatory pre-apply revalidation for every family; the action family's source is populate and its safety is a blocking Phase 2 gate question |
| 001: route alert acks and report runs through plans | full protocol | Record 007. One generalized gate, closed `operation` enum, per-family precondition fingerprints |
| sign-off markers missing fields | fast lane | Each marker re-authored by its own original reviewer (`bf93986`, `f462682`), peer-reviewed by claude-worker (`6beaa59`) |

The two 001 findings were dispatched as **one** assignment, because where
revalidation hooks depends on how the gate generalizes. All three doers
accepted the coupling.

## End-of-round sweep

Run at the close of this round, results recorded rather than assumed.

- **Open team PRs: zero.** PR #1 merged as `76c3357`.
- **Stale team branches: zero.** `round/1-architecture` deleted on both origin
  and locally by the merge. All 14 local doer branches deleted (round-1 three,
  round-2 gate three, round-2 signoffs three, plus five fix/review branches).
  Nothing is retained on purpose.
- **Doer-prefixed branches on origin: zero.** Guard run, passed. `origin` has
  `main` only, plus the 16 `artifacts/*` tags.
- **Worktrees** at `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-<doer>`
  were left in place, detached at `main`, for the next round to reuse. They hold
  untracked `scratch/` and `.team/markers/` from this round, which is permitted
  worktree scratch and does not merge.

## Next run starts here

1. **Confirm the DEVEL service account landed** (escalation 5) before scoping
   Phase 1 recon against it.
2. **Put escalation 6, the SPEC contract error, in front of Scott.** Phase 1 can
   proceed without it, but SPEC stays wrong until he rules.
3. **Scope the Phase 1 build round**: read-only tool families against DEVEL.
   Record 007's division of labor is prospective and ready to use. Action scopes
   stay ungrantable until Gate 2.
4. **Non-blocking sweep item** carried from round 1: the comment at
   `tools/consensus-check.py:516` still cites `001-town-motion.md`, a template
   leftover. Prose only, no behavioral effect. The `src/core/` and
   `ARCHITECTURE.md` strings elsewhere in that file are deliberate synthetic
   fixtures and must **not** be "fixed".

## Notes for the next run

### From the round-3 phase-1/2 run

- **Give workers the credentials path as an absolute path, and `--add-dir` it.**
  `.secrets/` is gitignored, so it does **not** exist in any worktree. A worker
  told to read `.secrets/vrops-credentials.txt` relative to its worktree finds
  nothing. Dispatch with
  `--add-dir /home/scott/foundry/projects/vcf-ops-mcp/.secrets` and give the
  absolute path in the prompt. All three doers then did live recon fine.
- **Extra adapter args go after a bare `--`.** `dispatch.sh` consumes its own
  flags and passes everything after `--` to the adapter, so the invocation is
  `"$D" claude <wt> <brief> <prompt> --cap-seconds N --label X -- --add-dir A
  --add-dir B`. Without the `--` the add-dirs are silently not passed.
- **The role-brief argument must be an absolute path.** `roles/codex-worker.md`
  relative to the project fails with "role-brief file not found"; the briefs
  live in `$TEAM_FRAMEWORK_DIR/roles/`. This cost one failed dispatch.
- **agy-worker does not reliably use the branch you check out for it.** On its
  proposal dispatch it created `agy/phase1-proposal` instead of using the
  provisioned `agy/p1-build`, and committed to the repo **root** rather than
  `docs/proposals/`. The work was real and complete, just misfiled: the end
  marker said `branch_changed: yes` while `git log round..agy/p1-build` was
  empty, which reads exactly like a dead dispatch and is not one. **Check
  `git branch --show-current` in the worktree and search for the commit before
  concluding anything was lost.** Telling it explicitly to use the checked-out
  branch fixed it on the critique dispatch.
- **agy-worker's trailer said `Antigravity <agy@team.local>`,** not
  `agy-worker`. The constitution requires the trailer name the resident. Worth
  stating the exact expected string in the dispatch prompt.
- **codex-worker wrote literal `\n` escapes into a commit message,** collapsing
  it to one physical line so the `Co-authored-by:` trailer was mid-line and git
  would not parse it as a trailer. It would have vanished at squash merge, which
  is the exact thing the trailer rule exists to prevent. Caught by
  `git log -1 --format='%(trailers:key=Co-authored-by)'`. **Run that check on
  every doer commit before integrating**, and put it in the prompt as a
  self-check.
- **Verify a load-bearing worker claim yourself, again.** claude-worker reported
  the service account sees only 4 objects. That drives an escalation, so the
  orchestrator measured it directly against DEVEL rather than relaying it:
  confirmed, `totalCount: 4` with 21 adapter kinds visible. This is the second
  round running where independently verifying one factual claim changed what
  got recorded.
- **Framing a discrepancy as "measure this, do not resolve it by authority"
  works.** The prompt named the `OpsToken` / `vRealizeOpsToken` conflict, said
  explicitly not to pick the more authoritative-looking source, and cited last
  round's near-miss as the reason. All three measured it and converged. Reuse
  this framing whenever two inputs disagree on a fact.
- **Naming the specific things to attack produced a real critique round.** The
  critique prompt listed six named targets and said plainly that a "looks good"
  round is a failed round that gets sent back. Result: every doer conceded at
  least one point, and two reversed positions from their own proposals on
  measurement. Compare a generic "critique the peers", which historically
  produces politeness.
- **Do not `git checkout <branch> -- TEAM-STATE.md` with uncommitted edits in
  the working tree.** This run lost a fully written state file that way and had
  to rewrite it from context. Commit the state file on the branch you edited it
  on, then merge; never restore it from another ref to "sync" it.
- **Dispatch wall clock this round:** SPEC edit 59s, trailer fix 68s, sign-off
  60s, three parallel proposals 580s (claude was slowest, agy 122s), three
  parallel critiques 476s. Caps of 1500s and 1200s were never approached.

### From the round-2 continuation run

- **Freeze artifact branches; put signatures on a separate branch.** A peer
  marker names an exact SHA and stops covering the branch the moment the branch
  moves. Round 2 kept `*/r2-mutation-gate` frozen at its ballot head and put the
  markers and record signatures on `*/r2-signoffs`. Without that split, every
  signature commit would have invalidated the marker written just before it.
- **Ask signers to confirm specific things, not to "sign off".** Each signature
  dispatch named the exact claims to confirm or deny (tally, dissent verbatim,
  concessions unsoftened, measurements unmisstated) and said plainly that
  withholding was a valid outcome. claude-worker then found **two real defects in
  the orchestrator's own record**: an unmarked truncation of its own concession
  quote, and missing timestamps on the `Signed-off-by:` lines that made
  `tools/consensus-check.py --self-test` fail at `6b7bdcf`. The self-test scans
  real records, so that one would have blocked CI. A generic "please sign"
  would not have surfaced either.
- **Run the gate yourself before opening or updating the PR.** Verified: the
  self-test failed at `6b7bdcf` and passes after the fix. Note
  `--changed-files` takes a **path to a file**, not a space-separated list;
  passing a list produces a `FileNotFoundError` traceback that looks like a
  tool bug and is not.
- **Verify a load-bearing cross-worker factual dispute yourself.** claude-worker
  and codex-worker contradicted each other on the alert verb set. The
  orchestrator checked the OpenAPI directly before synthesizing, rather than
  taking the more detailed proposal's word. codex-worker was right.
- **A confidently argued position can still reintroduce the defect.**
  agy-worker's critique concluded that actions should not be revalidated live at
  all, accepting the TOCTOU gap. That was well argued and would have undone the
  exact finding the round was convened to fix. It went to a ballot rather than
  being absorbed, and lost 4-0 including agy-worker's own vote.
- **Merge `main` into the round branch before opening the PR** if `TEAM-STATE.md`
  moved on `main` mid-round. The round branch carried a stale copy from when it
  was cut.

### From the original round-1 runs

- **The phase-1 near-miss, and the rule it produced.** Run `...-224036` was
  handed a confident premise that the phase-1 dispatch was dead and acted on
  it, dispatching a second full set of workers into the same three worktrees
  concurrently with live attempt-1 workers. A start marker with no end marker
  means "unknown", not "dead". Check for a live process
  (`ps -eo pid,etimes,cmd | grep dispatch.sh`) before concluding a dispatch
  died. Re-dispatching over live workers is strictly worse than waiting.
- **That kill was not as complete as the previous run recorded.** This run
  found that two duplicate workers survived the 22:43 kill and committed
  afterward: claude at `0ddea54` (22:51:33Z) and codex at `51e02f7`
  (22:45:54Z), both above their attempt-1 heads. The previous run's "no damage"
  verification was taken too early to see them. The duplicates were dispatched
  **without** `--add-dir`, so they could not read the SPEC section 2 knowledge
  directories, and claude's duplicate reached a materially weaker factual base
  (it reported a 401 and no live recon where attempt 1 measured 142 action
  definitions). Attempt-1 commits were therefore taken as canonical, branches
  were reset to them, and the duplicates are preserved at tags
  `archive/r1p1-claude-duplicate` and `archive/r1p1-codex-duplicate`.
  **Verify a kill by re-checking branch heads a few minutes later, not
  immediately.**
- **Cross-doer blindness was verified, not assumed.** Each doer branch's full
  file history was walked to confirm no branch ever contained a peer's proposal
  file. It did not. The duplicate contamination was intra-doer only, which is
  why phase 1 stood rather than needing a re-run.
- **Workers get `--add-dir /home/scott/claude/vcf-content-factory --add-dir
  /home/scott/claude/lab-admin`.** A worker without them cannot read the SPEC
  section 2 research inputs. Every dispatch this run carried them.
- **Marker timestamps are not always trustworthy.** claude-worker's phase-3
  signature and review markers both record `2026-07-20T23:38:12Z`, but the
  commit landed at `23:33:43Z`, about 4.5 minutes in the future. The signature
  is valid (the commit is real and git's commit time is authoritative), but
  prefer the git commit time over a self-reported marker time. The follow-up
  dispatch explicitly told the worker to read `date -u` and its next marker was
  accurate, so instructing it works.
- **Verify by end marker, never exit code.** Every dispatch this run was
  verified on `branch_sha_before`/`after`, `uncommitted_work`, and
  `cap_expired`. agy-worker's phase-2 marker reported `uncommitted_work: yes`;
  inspection showed untracked `scratch/` holding its read copies of the peer
  proposals, which is permitted worktree scratch and does not merge.
- **Dispatches are fast in this project.** Phase 2 took 224s wall clock for
  three parallel workers, phase 3 ballots 62s, sign-offs 75s. Caps of 900s and
  600s were never approached. Budget generously for synthesis and writing
  instead, which is where this run's time actually went.
- No dashboard/status-surface endpoint is configured in
  `.team/team-config.yaml`, so the narration section of the orchestrator brief
  is skipped. Nothing to post to.
- The framework install is at `/home/scott/foundry/tools/team-framework`
  (`$TEAM_FRAMEWORK_DIR`), a sibling of the project checkout, not inside it.
- This file lives on `main` deliberately, so a next run that reads `main` first
  can find it.
