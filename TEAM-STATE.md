# TEAM-STATE

Orchestrator durable state for vcf-ops-mcp. Read this first on every run,
update it before exiting. This is machinery, not a human changelog.

## Current assignment

**Round:** 4, the deploy-path repair (issue #4). Started as a spec round,
became a **build round** when the principal answered `approved`.
**Orchestrator run:** `gh-issue-4-execution-20260727-113452`
**Status:** Slice A is built, peer-signed, integrated, and **proven on the round
branch**. PR open to `main`, awaiting the external Codex review round.

### THE NEXT RUN STARTS HERE

1. **Check the round PR.** It is the single PR for round 4. If the external
   Codex review has landed, route each finding to its owning resident, get a
   non-author sign-off on each fix, integrate locally, and merge. One review
   round only, per keystone rule 2.
2. **Expect the post-merge `main` run to end RED at the health poll.** Designed,
   not broken. `/healthz` returns 503 by construction and that is issue #5
   (Slice B). Do not extend the timeout and do not re-run. The run is green
   through test, build, GHCR push, and the slot deploy.
3. **After merge:** write `.review-passed` straight to `main` (never its own
   PR), delete the round branch and every doer branch, run the sweep guard, and
   close #4 with the evidence.
4. **Issue #5 is Slice B**, claude-worker owning and codex-worker reviewing per
   011. It is the work that makes `/healthz` return 200.

### What this round established, and what it cost to establish

**The principal answered `approved` and nothing else.** The five decisions
round 4 escalated came back unanswered, so the orchestrator resolved all five
itself per keystone rule 5. They are recorded with their evidence in
`docs/decisions/012-slice-a-deploy-rewrite.md`. **Read 012 before 011**; it
changes what 011's workplan assumed.

**Decision 3 landed on the bad side, and it was settled from source rather than
by asking.** `~/claude/lab-admin/scripts/deploy-wrapper.sh` is the forced
command behind every slot key on `deploy@docker.int`. Its allowed verbs are
`scp` into the slot dir, `scp` of caddy artifacts, one legacy `rm`, and
`docker compose {pull|up -d|down|ps|restart|logs}`. **`vcf-ops-mcp get-digest`
does not exist and never did.** Every ssh the old deploy step made would have
been denied. Slice A therefore became a compose-file rewrite, hearthgate-shaped,
roughly double the size round 4 estimated.

**The authoritative document for anything touching docker.int is
`~/claude/lab-admin/docs/lab-container-host-contract.md` section 3.2.2.** Not
hearthgate's compose file, which is one caller of that contract and does not
show all of it. codex-worker worked from hearthgate and produced a compose file
violating three mandatory clauses. Point the next worker at the contract.

**Direct ssh to lab hosts is blocked at the tool layer.** Recon needing a lab
host goes through `/request-crossworkspace` to lab-admin. Everything this round
needed happened to be answerable from lab-admin's checked-in files.

**The framework artifact tools auto-commit and this repo has a naming scheme.**
`bin/team-record-artifact` commits as it goes, so a wrong `--round`/`--phase`
is a commit, not a stray file. This repo uses `round-N` / `phaseN`, not
`N` / `proposal`. Check `.team/provenance.md` for the established shape first.

### The peer review earned its cost, again

agy-worker **withheld** sign-off on `792f543` with three findings, all
independently matching what the orchestrator had already found from the
contract:

| # | Finding | Consequence had it shipped |
| --- | --- | --- |
| 1 | compose joins no `docker-slots` network | fleet-caddy has no route to the container at all |
| 2 | no resource limits, no logging cap | violates two mandatory contract clauses |
| 3 | `${SESSION_SECRET:?}` with no `.env` key for it | `docker compose pull` dies before the deploy starts, and the round proves nothing |

codex-worker fixed all three in `841612e` **without rebasing or amending**, so
the withholding marker still names the SHA it judged. Both markers are in
`.team/signoffs/`. Re-review granted at the new head.

Finding 3 is the one to remember: it would have produced a red deploy step that
looked like a slot or credential problem and was actually a compose file that
could not parse. That is the misdiagnosis this round was built to avoid.

### The round-branch proof worked, and it is the practice to keep

Decision 4 (publish images from `round/*`) paid for itself immediately. Run
`30263379624` on `round/4-deploy-permissions`:

- CI Pipeline: **success**
- Build and Push: **success**, digest
  `sha256:9839c5562d82518cc213d2c664ada2da5a8fdb61920d3e43be288845bde06607`
- Deploy: **skipped**, correctly, since the job is gated to `main`

**The GHCR push works. D1 is proven and the `main` merge was not spent proving
it.** The missing job-scoped `permissions: packages: write` really was the cause
of the original failure, and it really was not the only defect.

Integrated suite on the round branch before push: **126 passed, 13 skipped, 69
subtests**. Use a venv; a bare `python3 -m pytest` in a fresh worktree fails
collection on `ModuleNotFoundError: vcf_ops_mcp`.

### Configuration created this round, and the trap it avoided

| Name | Value | Kind |
| --- | --- | --- |
| `DOCKER_DEPLOY_HOST` | `deploy@docker.int.sentania.net` | repository **variable** |
| `SERVICE_URL` | `https://vcf-ops-mcp.int.sentania.net` | repository **variable** |

Neither is a credential. `DOCKER_DEPLOY_HOST` carries the `user@` part, matching
hearthgate, and the workflow's hardcoded `deploy@` prefix was deleted. Getting
this backwards yields `deploy@deploy@host`, which round 4 predicted and which
the preflight cannot catch because the value is non-empty.

**`DOCKER_DEPLOY_KEY` is still unverified as this slot's key** and deliberately
so. Secret values are unreadable and lab ssh is blocked, but the wrapper derives
the slot from `authorized_keys`, so a wrong key fails loudly on the first scp
with `deploy-wrapper: command not allowed`. That is a better oracle than an
attestation and it costs one run.

### Two things still unverified, both by design

- **The package's visibility and repo linkage were not read back.** The
  orchestrator's token lacks `read:packages`, exactly as the workplan predicted.
  The push succeeding is the proof that matters; the metadata read is not.
- **The slot's registered `upstream_service` and `upstream_port`.** The compose
  file uses `vcf-ops-mcp-web` on 8000, matching both the contract's `<slot>-web`
  convention and the image's `EXPOSE`. If the slot was registered against
  something else, the symptom is a 503 with a **running** container, which
  `docker compose ps` distinguishes from issue #5's 503.

### Branch state

`round/4-deploy-permissions` is **on `origin`** with an open PR; correct at this
stage, and it supersedes the local-only rule that governed it as a spec round.
Doer branches `codex/r4-slice-a` and `agy/r4-slice-a-review` plus the three
spec-phase doer branches are retained locally until the PR merges, then all are
deleted in the sweep. Every artifact they hold that a decision record cites is
already pinned under `docs/artifacts/round-4/` and ledgered in
`.team/provenance.md`, so deletion is safe.

### Carried items

- The non-`CancelledError` `BaseException` lease leak in the dispatcher.
  Fast-lane sized. See the round-3 section below.
- `bin/team-provenance-ledger` writes an em-dash. Belongs to the framework.
- **`main` has no branch protection**, so the consensus gate and CI are both
  advisory. Worth a deliberate decision rather than an accident.
- The deploy shell's recorded rough edges: `curl -k`, the 60-second health
  budget, and rollback having no digest source now that `get-digest` is known
  not to exist. All in `docs/proposals/4/WORKPLAN.md`'s follow-up list.
- Phase 2 remains gated on the principal. No action execution against a live
  appliance, never against prod.
- `.team/blocked/fleet-caddy-slot-config.md` is **closed out this round**.

---

### What round 4 actually found, and why it matters more than the issue did

Issue #4 said the missing `permissions:` block was "the only thing between
merged code and a running service." It was not. Five defects sit in that path
and the issue named one. The full evidence is in `SPEC.md` section 1; the two
that change what the team does:

- **Three of the four secrets the deploy step reads do not exist.** The
  workflow reads `DOCKER_INT_DEPLOY_KEY`, `DEPLOY_HOST`, `SERVICE_URL`. Repo
  secrets contain exactly `DOCKER_DEPLOY_KEY`. So the first run that gets past
  the permissions fix dies at an ssh to a host literally named `deploy@` with
  an empty key, and `|| echo "none"` swallows the one diagnostic signal.
  **This directly contradicts line 321 of this file's round-3 section**, which
  records the FQDNs moving "into `DEPLOY_HOST` / `SERVICE_URL` Actions
  secrets". The FQDNs came out of the workflow. The secrets were never created.
  A peer sign-off closed that item on the diff, because a diff is all a diff
  can show. **Do not trust a "moved to a secret" claim in this file again
  without reading the secret inventory.** The workplan's preflight step is the
  machine-enforced answer.
- **`/healthz` returns 503 by construction at every possible digest.** Uvicorn
  calls `create_app` with no arguments, `audit_repository` is `None`, and there
  is no concrete `AuditRepository` anywhere in `src/`. Separately the container
  raises on a `SESSION_SECRET` nothing supplies. So issue #4's second
  acceptance criterion is unreachable by any change to a CI file. codex-worker
  denied this same item in round 3 (`.team/signoffs/agy-r3-delivery-19efb0cdab60.md`,
  claim 4) and it was carried as PARTIALLY CLOSED. It has now caused a second
  round to be filed against an impossible criterion. It is Slice B and it needs
  a filed issue, not a third carry.

Established by measurement and worth keeping: hearthgate's GHCR package is
**private** and the docker.int host pulls it with no workflow-supplied
credential, so the host holds a daemon-level GHCR credential. A package
visibility flip is very likely not needed and is not a team-level workaround.
And hearthgate's deploy key runs arbitrary `scp` and `docker compose`, which
means this repo's `vcf-ops-mcp get-digest` forced-command grammar is
unattested and may not exist.

### Protocol notes from this round

- **Three-way blind proposal earned its cost here.** claude-worker found D2
  through D5, codex-worker independently found D2 and prescribed the winning
  permissions placement, agy-worker was refuted on its headline risk. A
  fast-laned three-line fix would have shipped and failed on `main`.
- **A ballot round was re-run rather than counted from the critiques**, because
  claude-worker dropped the `needs.build.outputs.digest` mechanism its peers
  had attacked. Counting the old critiques would have recorded votes against a
  proposal that no longer existed. Question A came back 4-0 for; the earlier
  critique split was 2-1 against.
- **The ratification round caught three defects in the orchestrator's own
  documents**, including a workplan that told a doer to push and ordered the
  round-branch proof before the integration that makes it possible. Signing the
  record is not ceremony. Keep doing it, and keep telling doers they may deny.
- **Artifact-only doer branches integrated without pre-integration sign-off
  markers**, per the round-1 precedent: doers ratify the decision record rather
  than signing each other's proposal documents. The sign-off gate applies in
  full to Slice A's implementation.
- **Exit codes were worthless again.** All twelve dispatches this run returned
  0. Verification came from `branch_sha_before`/`after` and `uncommitted_work`
  in the end markers, then from the tree.
- **The orchestrator re-verified every load-bearing claim itself** rather than
  taking it from a proposal: the `read` default workflow permission, the secret
  and variable inventories, `404 Branch not protected`, `app.py`'s 503 path and
  `SESSION_SECRET` raise, the absent `AuditRepository`, the absent compose
  file, the anonymous GHCR token responses, and hearthgate's `deploy.yml`
  shape. All confirmed as reported.

### Carried items, unchanged by this round

- The non-`CancelledError` `BaseException` lease leak in the dispatcher.
  Fast-lane sized. See the round-3 section below.
- `bin/team-provenance-ledger` writes an em-dash. Belongs to the framework.
- `.team/blocked/fleet-caddy-slot-config.md` is **resolved and should be closed
  out**; TLS now terminates and the proxy answers 503 rather than dying at
  Client Hello. It currently reads as open.
- Phase 2 remains gated on the principal. No action execution against a live
  appliance, never against prod.
- `main` has no branch protection, so the consensus gate and CI are both
  advisory. Worth a deliberate decision rather than an accident.

---

# Archive: round 3 and earlier

Everything below this line is the state as of the close of round 3. It is kept
for its findings, not as current status.

## Round 3 assignment (closed)

**Round:** 3, the Phase 1 build (first real code round)
**Orchestrator run:** `gh-issue-2-execution-20260726-014036` (external-review
run; supersedes every earlier run's state in this file)
**Status:** **ROUND 3 IS COMPLETE AND CLOSED.** PR #3 squash-merged to `main`
at `570fc3b`. The external Codex review's three findings were fixed by their
authoring residents, peer-signed by non-authors, and integrated. Integrated
suite at merge: 126 passed, 13 skipped, 69 subtests. `.review-passed` written
straight to `main` at `02d0f61`. Sweep clean: zero open PRs, zero local
branches other than `main`, zero doer branches on `origin`, zero process tags
on `origin`.

### THE NEXT RUN STARTS HERE

**There is no open round. Round 3 delivered Phase 1 and nothing is in
flight.** The next run opens round 4, and the first thing it does is triage.

1. **Read `docs/SPEC.md` and `docs/proposals/2/WORKPLAN.md`** to pick up what
   Phase 1 left for Phase 2. The workplan is the roadmap record 009 was built
   against.
2. **Two carried items belong to the team, not to the principal**, and both
   are recorded in full below. Neither is urgent and neither blocks Phase 2:
   - the non-`CancelledError` `BaseException` lease leak in the dispatcher
     (see "One known gap"), a few lines of change, fast-lane sized;
   - `bin/team-provenance-ledger` writing an em-dash, which belongs to
     whoever next touches the framework rather than to this project.
3. **Phase 2 is gated on Scott.** Action execution against a live appliance
   needs his Phase 2 gate approval, per `CLAUDE.md`. Do not dispatch anything
   that mutates a live appliance before it, and never against prod. Read-only
   recon against devel remains allowed.
4. **The fleet-caddy blocker is still open externally** and still does not
   block the team. See the section near the end of this head.

Merge `origin/main` into the round branch before opening the round PR, not
after. See "The `origin/main` conflict" below for why this recurs every round.

### The external review found three real defects, one per slice owner

`chatgpt-codex-connector` reviewed `7180ba2` automatically at
2026-07-26T01:30:31Z. Three findings, and they partitioned cleanly by
authorship, so each went back to the resident that wrote the code.

| # | Finding | Sev | Owner | Reviewer | Signed SHA |
| --- | --- | --- | --- | --- | --- |
| 1 | audit lease leaks on `CancelledError` | P1 | codex-worker | claude-worker | `59f5c2e` |
| 2 | deploy key survives early exit | P1 | agy-worker | codex-worker | `3a58ba7` |
| 3 | response cap checked after buffering | P2 | claude-worker | agy-worker | `e88f4c1` |

No resident reviewed its own work. Every fix merged at its reviewed SHA
without rebase, so each marker still names the exact commit it covers.

### Finding 2 took four passes, and the escalation was correct each time

This is the one worth reading. codex-worker withheld sign-off **three times**
on the deploy key fix, and every withhold was substantiated rather than
stylistic. The sequence:

- `106a317`, agy installed the `EXIT` trap after `chmod 600`. Withheld: if
  `chmod` fails under error exit, Bash leaves the step before the trap is
  installed and the key stays in the checkout.
- `e1ff831`, agy moved the trap ahead of `chmod`. Withheld again, and this is
  the ruling that mattered: **the deploy job runs on a self-hosted runner, so
  the checkout is reusable rather than ephemeral.** A partial key stranded
  there persists indefinitely, so the narrowness of the remaining write window
  does not bound the harm. codex prescribed the design: key under
  `$RUNNER_TEMP`, trap installed before any write.
- `2e8d353`, agy implemented that design with `install -m 600 /dev/null`,
  which also closes the mode window entirely. Withheld a third time on two
  narrow defects, both **tested rather than asserted**: agy's commit message
  claimed an empty `$RUNNER_TEMP` would resolve to `/deploy_key` and "safely
  fail on write due to lack of root permissions", and codex probed it and
  found root can write `/`; and `trap "rm -f '$KEY_PATH'" EXIT` interpolates
  the path into shell source, which codex broke with an apostrophe.
- `3a58ba7`, agy applied codex's prescribed two lines. **Signed off.**

The final shape:

```sh
: "${RUNNER_TEMP:?RUNNER_TEMP must be set and nonempty}"
KEY_PATH="$RUNNER_TEMP/deploy_key"
trap 'rm -f -- "$KEY_PATH"' EXIT
install -m 600 /dev/null "$KEY_PATH"
echo "$DEPLOY_KEY" > "$KEY_PATH"
```

Note the external reviewer offered two designs, "install an `EXIT` trap
immediately after creating the file, **or** supply the key without writing it
into the checkout". agy built the first and codex ruled that only the second is
sufficient on a self-hosted runner. **The peer review was right and the
external review's first option was not good enough for this repo.** That is
the pre-integration layer doing exactly what it exists for.

Three withholds on one workflow file is a lot of passes. It was not a loop:
each round was strictly narrower than the last and each ended with a concrete
prescribed construction rather than an objection. The orchestrator's fourth
dispatch said so explicitly, telling codex the bar was whether key material can
be stranded and not whether the workflow could be tidier.

### Both regression tests were verified against unfixed code, one by the orchestrator

The standing problem with a "regression test" is that it can pass on the code
it was supposed to catch. Both were checked.

claude-worker, reviewing finding 1, exported `e73bad5` and ran codex's new test
against it. It reproduced **both halves** of the finding independently: the
terminal row is never written (`['attempt'] != ['attempt', 'cancelled']`) and,
after patching out the audit assertion, the lease is never released
(`32960 != 0`, exactly one `CALL_RESERVATION_BYTES`). The ratchet in the
finding is real, not theoretical.

agy-worker's sign-off on finding 3 claimed the same kind of verification, and
**the orchestrator ran it independently** rather than taking the report, per
this file's standing practice for that seat:

    AssertionError: 10485760 not less than or equal to 8454144

The test asserts on peak accumulation, not on the exception. That distinction
is load-bearing: the pre-fix code raises the *same* `ResultCapExceeded` while
having already buffered the whole body, so a test asserting only on the raise
would have passed against unfixed code and proven nothing. The claim holds.

### One known gap, deliberately not fixed, do not lose it

claude-worker found it while reviewing finding 1 and declined to withhold
sign-off over it, correctly. Recording it here so it survives.

**A handler raising a `BaseException` that is not `CancelledError` still leaks
the lease.** Confirmed against the fixed code with both a custom
`BaseException` subclass and a `KeyboardInterrupt`: rows `['attempt']`,
`reserved: 32960` in each case. Finalization is keyed on
`except asyncio.CancelledError` rather than `except BaseException`.

Why it is not a blocker: the realistic members of that set,
`KeyboardInterrupt` and `SystemExit`, end the process, which takes the
process-local reservation with it. The gap is pre-existing rather than
introduced by the fix, and it sits outside the finding the commit was
dispatched to close. Widening the clause to `except BaseException` with an
unconditional re-raise closes it in a few lines. **Worth a later slice.**

A second, smaller one from the same review: under a second `cancel()` arriving
while the terminal audit write is suspended, the terminal row is lost but the
lease is still released, so the ratchet stays closed. The lost row is covered
by the `AuditRepository` reconciliation contract, which closes attempts lacking
a terminal record as `outcome_unknown` and never infers success.

### Protected paths: no new decision record was needed

Findings 1 and 3 both touch `src/vcf_ops_mcp/`, which is protected.
claude-worker checked this properly: `tools/consensus-check.py` passes against
a PR body naming `docs/decisions/009-phase1-build-synthesis.md`, which is
accepted, principal-approved, signed by all three doers, and already names
`src/vcf_ops_mcp/` as in scope. These are defect fixes inside that record's
scope, not new architectural decisions. `AuditStatus.CANCELLED` is additive to
a `StrEnum` with no ordinal dependency, no exhaustive dispatch anywhere in
`src/`, and no concrete `AuditRepository` yet, so nothing needs migrating.

Finding 2 touches only `.github/workflows/`, which is not protected.

### Resolved blocked markers that were deliberately not merged

Four blocked markers were written during this run and **none of them are in
the round branch**, because every one is resolved and a resolved block sitting
in `.team/blocked/` reads as an open one.

- `agy-worker-20260726T014226Z` on `agy/r3-fix-deploykey` at `d7deee2`, asking
  the orchestrator to name a reviewer. It was answered by the dispatch of the
  review itself. Only the fix commit `106a317` was carried forward.
- Three from codex-worker recording the withheld sign-offs, at `74f5364`,
  `6a9430b`, and `7f1d3ff`. Their substance is quoted above, which is where it
  belongs, since these are review findings rather than decision-record
  artifacts and no record cites their SHAs.

### The `origin/main` conflict, and why it recurs

PR #3 went `CONFLICTING` between runs because `main` advanced with two
orchestrator state commits (`d84b1d7`, `ca5f0dc`) while the round branch held
an older `TEAM-STATE.md`. Only `TEAM-STATE.md` conflicted; nothing else in
21,000 lines of diff did. Resolved by merging `origin/main` into the round
branch and rewriting the head section, which is this text.

**This will happen on every round** as long as orchestrator state commits go
straight to `main` while a round branch is open. It is cheap to resolve and the
file is orchestrator-owned, so no worker is ever blocked by it. Merge
`origin/main` into the round branch before opening the PR, not after.

### Dispatch mechanics: still true, still worth not repeating

- **`roles/<seat>.md` as a relative path fails.** The briefs live in
  `$TEAM_FRAMEWORK_DIR/roles/`, not in this repo. Always pass the absolute
  path. This run did and had no dispatch failures.
- **Exit codes are worthless; read the end markers.** All seven dispatches this
  run returned 0. Verification came from `branch_sha_before` versus
  `branch_sha_after` and `uncommitted_work` in each end marker, then from the
  tree itself.
- **The end marker can lag the dispatcher's return by a second or two.** Two
  checks this run reported "NO END MARKER" against a marker that existed
  moments later. `sleep 3` before globbing, and do not conclude a dispatch
  failed on a first miss.
- **agy-worker's short dispatches remain worth spot-checking.** Its 1m00s
  review of finding 3 was correct on every point, verified independently. Four
  rounds of flagging this seat, four rounds of the work being fine.

### Final slice status, round 3

| Slice | Owner | Reviewer | Signed SHA | Integrated |
| --- | --- | --- | --- | --- |
| spine | codex-worker | claude-worker | `cd08783` | yes |
| read plane | claude-worker | agy-worker | `7f942f7` | yes |
| delivery | agy-worker | codex-worker | `5bd75c6` | yes |
| skills | agy-worker | claude-worker | `6ffe808` | yes |
| ext. review 1, cancel | codex-worker | claude-worker | `59f5c2e` | yes, this run |
| ext. review 2, deploy key | agy-worker | codex-worker | `3a58ba7` | yes, this run |
| ext. review 3, stream cap | claude-worker | agy-worker | `e88f4c1` | yes, this run |

### The suite command matters, and a bare `pytest` is not it

An ambient `pytest` without an editable install collects zero tests and reports
errors that look like failures. codex-worker hit this again this run and
correctly diagnosed it as environment setup rather than a test failure. The
orchestrator's own integration run used `git archive` to `/tmp`, a fresh venv,
`pip install -e .[test]`, then `pytest tests/`. Use that.

### Provenance is recorded, so the branches are safe to delete

Record 009 cites 17 SHAs. Sixteen documents (three proposals, three critiques,
three complete Q7 ballots, three superseded Q1-Q6 ballot heads, three
signatures, and codex-worker's withholding) are copied in-tree under
`docs/artifacts/round-3/` with provenance headers, each joined to its cited SHA
by a row in `.team/provenance.md`. This was done **before** any branch deletion,
per the convention. The seventeenth is the round branch's own commit, already in
the tree.

Note that agy-worker's proposal is at `phase1-proposal.md` in the **repo root**
at `f136b2a`, not under `docs/proposals/`; it ignored the convention that round
and the recording had to account for it.

The seven fix and review branches this run created cite no SHAs from any
decision record, so they need no artifact recording before deletion. They were
deleted in the closing sweep along with every other round and doer branch.

### Sweep result, round 3 close

Run at close, per the brief. All four assertions passed:

- **Zero open team PRs.** PR #3 merged at `570fc3b`.
- **Zero stale local branches.** `main` only. Every round, doer, fix, and
  review branch deleted, along with all 20 worktrees.
- **Zero doer-prefixed branches on `origin`.** The guard ran and exited clean.
- **Zero process tags on `origin`.**

This is the first round to close with nothing retained, which is what the
brief said to expect.

### Record 010: verbatim artifacts are exempt from the dash rule

`docs/decisions/010-verbatim-artifacts-exempt-from-the-dash-rule.md`. The
en-dashes are in the cursor critic's tiebreaking vote, recorded verbatim. A
transcription is evidence and is not edited. Reviewers should use the excluded
form, and **the trailing `*` is load-bearing**:

    git grep -nP '[\x{2014}\x{2013}]' -- . \
      ':!docs/proposals/*/ballots/*' ':!.team/votes/'

A reviewer who reports this again should be pointed at record 010 rather than
re-litigating it.

### The framework writes an em-dash into this repo

`bin/team-provenance-ledger` writes `.team/provenance.md`'s header with an
em-dash on first use, violating this repo's hard rule. Corrected by hand at
`493aaac`; the tool only appends rows afterward, so the fix is stable. **Fixing
it upstream in the framework is a real but non-blocking item** and belongs to
whoever next touches the framework, not to this project's round.

### Untracked orchestrator markers in the primary checkout

Orchestrator `.team/markers/` files sit untracked in the primary checkout and
predate this run. They are deliberately not committed and are not in the PR.
`gh pr create` warns about them; the warning is expected and is not a problem.

### The fleet-caddy blocker is still open and still not blocking

`.team/blocked/fleet-caddy-slot-config.md`. Per-slot config is missing on
docker.int, relayed to lab-admin 2026-07-25 (PKA request `e91b47d2`). The
`Build & Deploy` job skips correctly because of it. Nothing in the round
depends on it. Do not wait on it.

---

## Historical, superseded by the sections above

Everything below this line describes earlier runs of round 3 and is retained
for the audit trail. Where it conflicts with the sections above, the sections
above win.

### THE NEXT RUN STARTS HERE, read this first

**Two slices remain unsigned and each needs one short fix dispatch, then one
short re-review. Both worklists are exact and small.** The spine and the read
plane are both signed and integrated; the round branch is green at 103 tests.

1. **`agy/r3-delivery` at `11b0227`, re-reviewed by codex-worker,
   changes-requested. Two Tier 1 items block it, both mechanical.**
   - **Restore eleven files the cleanup deleted that predate this slice.** The
     removal of the 45 slice-local artifacts was correct and must stay. These
     eleven existed at `33bca5d` and are not this slice's to delete: six
     `.team/markers/orchestrator-run-20260720-*` files, four
     `.team/markers/stale/*DUPLICATE*` files, and
     `.team/markers/vom-r2-esc-20260721-171423-start.md`. The exact list is in
     the marker.
   - **Six trailing-whitespace errors** from `git diff --check 19efb0c..11b0227`,
     including `src/vcf_ops_mcp/app.py:60` and `tests/test_admin.py:23`.

   Tier 1 items 2, 3, and 5 are CLOSED: the lab FQDNs are out of the workflow
   and into `DEPLOY_HOST` / `SERVICE_URL` Actions secrets; `post_login` now
   returns an explicit 501 and `create_app` raises `RuntimeError` without
   `SESSION_SECRET`, so both literals are gone and the fail-closed alternative
   is the allowed one; and the runner model is pinned. Volume declarations are
   CLOSED. Six Tier 2 items are PARTIALLY CLOSED and are the next increment's
   worklist; the marker states each one's remainder.

2. **`agy/r3-skills` at `88530b3`, re-reviewed by claude-worker,
   changes-requested on exactly one item.** Blocking items 1 and 3 are CLOSED
   and nothing regressed. Item 2's **sort is correct and proven**; its **test
   does not hold the guarantee**. claude-worker deleted the sort line and the
   suite stayed 8 of 8 green, because the two-entry fixture (`z-skill`,
   `a-skill`) comes back from readdir already sorted on this filesystem, so the
   assertion cannot distinguish sorted output from readdir output. The fix it
   asked for: build enough slugs that readdir demonstrably scrambles (twelve
   worked), then assert both that the generated slugs are sorted **and** that
   the raw `iterdir()` order was not already sorted, so the test fails loudly if
   the fixture stops scrambling rather than passing for the wrong reason.

3. **Reuse the review worktrees and branches.** `-rev-claude`
   (`claude/r3-rev-spine`), `-rev-claude2` (`claude/r3-rev-skills`), `-rev-agy`
   (`agy/r3-rev-readplane`), `-rev-codex` (`codex/r3-rev-delivery`), under
   `/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-`. All are merged into
   the round branch; reset each to the round head and reuse it. Pass the
   author's worktree as `--add-dir` so the reviewer can run tests read-only
   where the slice is checked out, and let it commit its marker in its own.
   Rotation holds: codex reviews delivery, claude reviews skills.

4. **Then the round PR.** Once delivery and skills are signed and integrated
   green, the round branch is complete: contracts, both spikes, and all four
   slices. Squash to one commit naming the round and record 009 with a
   `Co-authored-by:` trailer per doer, run `bin/team-record-artifact` and
   `bin/team-provenance-ledger` for every proposal, critique, and ballot SHA
   record 009 cites **before** deleting any branch, then open the single round
   PR referencing issue #2.

5. **Two repo-level items need an orchestrator ruling, neither is a doer's.**
   - **An en-dash in `docs/proposals/2/ballots/critic-r3-skills-ownership-vote.md:8`**
     makes the repo-wide `git grep -nP '[\x{2014}\x{2013}]'` fail at the
     repository baseline. Found independently by two reviewers. It is inside the
     **critic's vote, recorded verbatim**. The no-em-dash rule is a hard repo
     rule; recording a vote verbatim is also a hard rule, and they conflict.
     Do not quietly edit a verbatim quotation. A marked bracketed transcription
     note is probably right, but it is a ruling, so make it explicitly and
     record it.
   - **No `pyproject.toml`, `conftest.py`, or `pytest.ini` on the round branch**
     at the time of review, so a bare `pytest` failed collection with
     `ModuleNotFoundError: No module named 'vcf_ops_mcp'`. `agy/r3-delivery`
     adds a `pyproject.toml`, so this closes when delivery integrates. Confirm
     it lands, because CI runs the literal command.

6. **Do not re-run spike 002** until the fleet-caddy blocker clears. Watch #2.

7. **No PR is open and the round branch is still local.** Correct until item 4.

### The peer-review round: what it found

Four reviews, four end markers, all `branch_changed: yes`, none cap-expired,
none with uncommitted work. Dispatched in parallel into four fresh review
worktrees, 123 to 329 seconds each.

| Slice | SHA reviewed | Reviewer | Result | Marker |
| --- | --- | --- | --- | --- |
| spine | `123d9fb` | claude-worker | changes-requested | `codex-r3-spine-123d9fb8bad9.md` |
| read plane | `7f942f7` | agy-worker | **signed** | `claude-r3-readplane-7f942f789de7.md` |
| delivery | `19efb0c` | codex-worker | changes-requested | `agy-r3-delivery-19efb0cdab60.md` |
| skills | `41909bb` | claude-worker | changes-requested | `agy-r3-skills-41909bb8da77.md` |

**The named-claims framing worked for a fourth consecutive round, and this time
it caught a constitution violation.** Each prompt listed 7 to 10 specific claims
to confirm or deny and said withholding was valid. Read the markers; they are
327 to 409 lines each and cite file and line.

The three findings that matter most:

- **Spine: no denial produces an audit row.** claude-worker probed the real
  dispatcher and got **zero** audit rows for revoked-key, empty-scope,
  no-identity, unknown-tool, and non-JSON-args denials. `AuditStatus.DENIED` and
  `TerminalState.DENIED` are defined in `contracts.py` and nothing produces
  them, while the commit lists "request-local authorization, posture gating" as
  Done. `CLAUDE.md` is unconditional: no tool path ships without its audit write,
  and a denied call is a tool call. This is a direct invariant violation that
  three prior artifacts (the commit message, the spike, the record) all read as
  covered.
- **Delivery: nine of ten claims denied, including three constitution items.**
  Lab host and service FQDNs hard-coded in `.github/workflows/ai-log-depot.yml`;
  a literal password `"admin"` in the login route and a fixed session secret
  `"change_me_in_production_from_env_var"` in the production factory; and
  **4,101 lines of unrelated material committed** (34 historical `.team/markers`
  files, two `.patch` files, `diff.txt`, `log.txt`, nine `scratch/` proposal and
  critique files). codex-worker's phrase for the pattern is the useful one and is
  worth quoting to that seat again: the slice "introduces security-critical
  placeholders that look operational". `/healthz` returns a plausible `0`
  unreconciled count in the exact path the Dockerfile invokes.
- **Skills: the auth walkthrough placeholder ships as a finished skill.** Its
  metadata is byte-identical to the real skills in the `maturity` field, the
  index lists it in `current` with a digest, and all four render paths serve a
  body of `[SLOT: claude-worker auth walkthrough content]` under a summary
  promising an auth flow. A model that calls it improvises an auth flow, which
  for this skill means guessing at credentials. Also: the index generator emits
  `Path.iterdir()` order and is not sorted, so a regenerate-and-diff CI check is
  one skill away from spurious failure; it looks stable today only because
  ext4's hash order for these three slugs happens to be alphabetical, which
  claude-worker demonstrated with twelve slugs.

### The read plane is signed, integrated, and the sign-off was verified

`claude/r3-readplane` at `7f942f7` merged into the round branch at `d509199`,
**without rebase**, so the reviewed SHA is preserved. 5506 lines, three commits,
25 files. All 91 tests green on the integrated branch.

**agy-worker's marker was independently verified by the orchestrator before the
merge**, because a 123-second, 27-line sign-off on a 5506-line slice is exactly
the pattern this file has flagged for two rounds. The result is worth recording
precisely rather than by reputation:

- **Every checkable claim in it resolves true.** All five named test functions
  exist in `tests/test_vcf_client.py`; the fixture-generator negative control
  exists at `test_vcf_fixture_generator.py:130`; `tests/live/guard.py` has
  `PROD_FQDN`, an import-time `assert PROD_FQDN not in LIVE_HOST_ALLOWLIST`, and
  the `refuse_outside_the_read_set` hook; `contracts.py` is untouched by the
  branch. The suite was re-run by the orchestrator: 91 passed.
- **One imprecision, not a defect.** Its claim 7 said the counts 517/1216/879/142
  appear "only in comments or mock fixture string inputs". One appears inside an
  `assertEqual` at `test_vcf_fixture_generator.py:289`. Read in context, that is
  a scrubber round-trip test asserting a number in **synthetic input** survives
  scrubbing, not a contract test asserting an appliance object count, so the
  acceptance criterion holds and so does the substance of the claim.
- **This is a genuine improvement on the last two rounds and should be recorded
  as such.** The prompt named the depth pattern explicitly and asked for
  calibration, and the marker came back citing specific test functions and files
  rather than confirming items with no specifics. It is still the shortest review
  of the round by a wide margin, on the second-largest slice, so keep naming it.
  But it is checkable, and it checked out.

### Two trailer defects: fixed before sign-off, and this ordering matters

Both were amended by their own authors before any marker named a SHA, because a
trailer fix rewrites the commit and a marker naming the old SHA would stop
covering it.

| Branch | Was | Now | New SHA |
| --- | --- | --- | --- |
| `codex/r3-spine` | `Codex <codex@team.local>` | `codex-worker <codex@team.local>` | `123d9fb8bad9d23b03c63fbda7f7dbe50ac50c08` |
| `agy/r3-skills` | `Antigravity <agy@team.local>` | `agy-worker <agy@team.local>` | `41909bb8da77a97a1ada47301f45ab3379cbe3b0` |

Both amends were message-only and verified: `git diff --stat <old> <new>` is
empty for both. **Stating the exact expected trailer string in the prompt worked
on the first attempt for both seats**, including the agy seat that had produced
this defect two rounds running. Keep doing that.

### Slice status after this run

| Slice | Owner | Branch | SHA reviewed | Review | State |
| --- | --- | --- | --- | --- | --- |
| spine | codex-worker | `codex/r3-spine` | `cd08783` | **signed** | **integrated at `cc1007a`** |
| read plane | claude-worker | `claude/r3-readplane` | `7f942f7` | **signed** | **integrated at `d509199`** |
| delivery | agy-worker | `agy/r3-delivery` | `11b0227` | changes-requested | 2 mechanical Tier 1 items open |
| skills | agy-worker | `agy/r3-skills` | `88530b3` | changes-requested | 1 item open, a test that does not hold its guarantee |

Seven review markers are in the tree: four first-round and three re-review. The
first-round `changes-requested` markers stay as the record of that round.

**The spine's re-review is the round's best artifact.** claude-worker probed the
real dispatcher again rather than reading the new tests, and confirmed all four
of its blocking items closed, including the constitution one: denials now write
audit rows. Signed at `cd08783`.

**Two re-reviews found defects a reading review would have missed, both by
mutation.** claude-worker deleted the skills sort line and watched the suite
stay green, proving the new test could not distinguish sorted output from
readdir order. codex-worker diffed the delivery cleanup against the pre-slice
baseline and found it had deleted eleven files that predated the slice along
with the 45 it was asked to remove. Neither is visible by reading the diff.

The skills slice keeps the critic's binding rider (distinct workplan item,
distinct review, non-blocking relative to the Gate 1 deploy). claude-worker
confirmed the rider is intact structurally: the branch does not import from or
depend on delivery.

**claude-worker owes the suite-api auth walkthrough content**, per WORKPLAN:139,
and said so unprompted in its skills review. The one fact it must carry, recorded
here so it survives: the local auth source value the suite-api expects is
`LOCAL`, not the admin picker's display label "Local Users", which produces a 401
indistinguishable from a wrong password. The delivery slice has the same defect
in its picker and it is item 6 of that redispatch.

### Step 0 spike results, both complete

| Spike | Owner | Verdict | Artifact | Branch, unmerged |
| --- | --- | --- | --- | --- |
| 001 FastMCP identity injection | codex-worker | **PASS** | `6d00202f402d1644e2b19f97e27c8ca884d61180` | `codex/r3-spike-identity` |
| 002 Streamable HTTP through fleet-caddy | agy-worker | **BLOCKED** | `dbe1168` | `agy/r3-spike-transport` |

**Spike 001 unblocks the dispatcher and pins its contract.** `mcp==1.28.1`,
identity read via `ctx.request_context.request.state`, correct under two
concurrent sessions. The load-bearing finding is that **identity belongs to the
HTTP request, not the MCP session**: codex changed the key header mid-session
and the handler saw the new one. So caching identity on the session would
silently misattribute audit records, and the same-session key-change case is now
a required test. It also flagged that it tested exactly `1.28.1`, not every
patch, and that `mcp.server.auth.middleware.auth_context.get_access_token` is a
different mechanism it did not test.

**Spike 002 is the blocker.** See `.team/blocked/fleet-caddy-slot-config.md`.
The fleet-caddy per-slot config for this project is missing (`/etc/caddy/conf.d/
vcf-ops-mcp` is empty inside the container), so TLS dies at Client Hello. DNS
resolves and `DOCKER_DEPLOY_KEY` exists, so only the caddy half of the handoff is
missing. agy-worker correctly **stopped rather than substituting a local proxy**,
so the proxy question (buffering, idle timeout, header forwarding) is genuinely
unanswered. Escalated to the principal on issue #2. **Blocks only the delivery
slice's deploy verification and Gate 1's connect step**; everything else
proceeds.

### Owed by the next run, do not lose these

- **CLEARED 2026-07-25: peer sign-off markers for both spike branches.**
  claude-worker reviewed and signed both at `71633c7`, and both spike branches
  are now merged into the round branch (`e36ec7e`, `0481355`, `3b6e156`).
  Markers: `.team/signoffs/codex-r3-spike-identity-6d00202f402d.md` and
  `agy-r3-spike-transport-dbe11684f4dd.md`.
- **A process error of this run, recorded so it is not repeated.** The agy spike
  dispatch was killed by the orchestrator's own tool timeout at 10 minutes, not
  by its cap and not by any worker fault. It had already committed `dbe1168`, so
  no work was lost and the doc is complete, but **no end marker was written**.
  A missing end marker here means "the orchestrator killed it", not "the worker
  died". The lesson: the harness's Bash timeout ceiling is 10 minutes, so a
  dispatch with a longer cap must be launched and then polled in a separate
  call, never waited on inline with `wait`.

### The approval, and what it settled

The principal commented exactly `approved` on issue #2 at 2026-07-24T21:41:47Z.
Recorded as **record 009 Amendment 1**, which reads an unconditional approval of
a spec that states its own answers as approving those answers: reports
definitions-only, TLS verification off for the first DEVEL registration with a CA
bundle preferred and still his call, and the decision 7-sub audit-invariant
reading. All three stay open for him to overrule.

### The sign-off round found real defects. Record 009 Amendment 2

**codex-worker withheld its signature and was right to.** Its
fingerprint-pinning objection had been paraphrased in a section where both other
objections were verbatim quotes. claude-worker separately found that its own
reports objection was front-truncated, dropping its only procedural objection of
the round, plus two unmarked tail truncations. **The orchestrator verified every
claim against the ballots rather than taking them on report**, fixed all of it,
and codex-worker signed after. This is the second consecutive round where asking
signers to confirm *named specific claims* rather than to "sign off" caught
defects in the orchestrator's own record. Keep using that framing.

Four rulings in Amendment 2, none of which changes a decision:

1. **Numeric thresholds belong to the slice owner**, derived, declared, tested,
   and put in the Gate 1 packet. Applies symmetrically to codex's free-space
   reservation and claude's metrics cap. codex additionally owes the reservation
   **accounting semantics** (terminal row, WAL growth, checkpoint headroom, and
   how concurrent admitted calls consume and release it), which was the real gap
   in its objection.
2. **`contracts.py` carries a target-change invalidation protocol** at step 1.
3. **Reports scope is now a Gate 1 packet item.** claude-worker checked
   Amendment 1's claim that all three questions were packet items and found it
   false for reports, which had no scheduled re-ask.
4. **The audit-invariant reading goes to the principal ahead of Gate 1**, not
   only in the packet, because changing that terminal contract late is
   expensive. Asked on issue #2 this run.

### Signature artifacts, round 3 implementation dispatch

| Doer | Signature | Branch |
| --- | --- | --- |
| claude-worker | `92cf4a4f6c4cb40c2464a962c80af90a635211dc` | `claude/r3-signoffs` |
| codex-worker | `bebc4ac448bb9600acb98c30439ab2d241974450` | `codex/r3-signoffs` |
| agy-worker | `27f0e3c06763f5fc93fccbc09d0ad3b0adf8746e` | `agy/r3-signoffs` |

codex-worker's withholding is preserved at `c3f392c730f472461dd4a7e9e271968f2ae91da2`.
All three signature files are copied verbatim into `docs/decisions/signatures/`
on the round branch, so they survive branch deletion.

**Depth was not comparable and the next run should weigh it accordingly:**
claude 256 lines and four of the five findings, codex 69 lines and the
withholding, **agy 8 lines in a 96-second dispatch confirming all six items with
no specifics**, including that the acceptance criteria for the largest slice in
the plan (delivery, 8 to 12 days, its own) are "unambiguous, directly testable,
and buildable as written". Its one checkable claim, that its own objection is
quoted verbatim, was independently verified and is true. Recorded in 009's
Amendment 2 process note. This is the second consecutive round with the least
scrutiny from this seat on the largest slice. Its spike work this run, by
contrast, was honest and correct.

### Historical: the triage run's status, now superseded

The round previously sat parked awaiting approval under run
`gh-issue-2-triage-20260724-205415`. That gate is closed. The sections below
from "Deliverable of this run" onward describe that earlier run and are context,
not current state.

**The Gate 1 blocker is CLOSED**, re-verified live by this run rather than taken
on relay. See "Escalations".

Round 1 and round 2 are complete and their history is preserved further down
this file, from "Continuation scope, given by Scott" onward. Read the round-3
sections first; the older sections are context, not current state.

### Deliverable of this run

`docs/proposals/2/` on the round branch, per the GitHub-issue pipeline contract:
`TLDR.md` (what the principal actually reads), `SPEC.md` (the consensus build
spec), `WORKPLAN.md` (slices, owners, sequencing, acceptance criteria), and
`ballots/` (all four ballots plus the critic's vote). A deterministic wrapper,
not this run, reads that directory off the round branch and posts it to issue
#2. **No PR was opened and nothing merged to `main`**, per the assignment.

The synthesis itself is `docs/decisions/009-phase1-build-synthesis.md`, which
carries every ballot result, every losing objection verbatim, and the critic's
tiebreaking vote verbatim. **009 is unsigned on purpose**; sign-offs from all
three doers are collected at implementation dispatch, since this round
authorizes no code.

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
| 3 ballots + synthesis | **done** | 7 questions, 4 ballots each, one 2-2 split decided by the critic; record 009 |
| implementation | **blocked on approval** | gated on the principal approving `docs/proposals/2/` on issue #2 |

### Ballot artifact SHAs, round 3 phase 3

| Doer | Ballot (Q1-Q6) | Q7 ballot |
| --- | --- | --- |
| claude-worker | `20bca552980521f73908759d6843505ac01a3fdf` | `a7c210a51f11231d0bd087d0a01a20a047bc55eb` |
| codex-worker | `e191214a9a86c5c674dfa9e7fe7bc7004377925a` | `ef60f4d20e674e681377a67737662ceab6407191` |
| agy-worker | `75bfc1f67e049d72a7e0011b54c93063ab7a144d` | `612bbe6ce7e33be9dabcb153be799c6b1b4ec193` |

The Q7 SHAs supersede the Q1-Q6 SHAs (each doer appended Q7 to its own ballot
file), so the Q7 commit is the complete ballot. Both are cited in record 009.
Ballot branches: `claude/p1-ballot`, `codex/p1-ballot`, `agy/p1-ballot`. Copies
of all four ballots and the critic vote are committed under
`docs/proposals/2/ballots/` on the round branch, so they survive branch deletion
without needing the artifact-recording tooling.

### Results, round 3 phase 3

| # | Question | Result | Vote |
| --- | --- | --- | --- |
| 1 | Audit unavailability blocks startup? | No (1B), plus a binding admin-write rider | 4-0 |
| 2 | Audit storage | SQLite, no rotation (2C) | 3-1, agy dissenting |
| 3 | Fixtures | 3B plus four corrections | 3-1, agy dissenting |
| 4 | Retry bound | 4B, explicit per-request counter | 4-0 |
| 5 | Enforcement predicate | 5B, capability plus frozen allowlist | 4-0 |
| 5-sub | Test-only mutating capability | Yes | 4-0 |
| 6 | Decomposition | 6B, spine plus two corrections | 4-0 |
| 6-sub | Three main slice owners | codex spine, claude read plane, agy delivery | 4-0 |
| 6-sub | Skills owner | **agy-worker** | **2-2, critic decided** |
| 7 | Terminal audit write failure | 7C-with-payload | 4-0 |
| 7-sub | Escalate the invariant reading? | No, with two conditions | 4-0 |

**The critic seat fired for the first time in this project.** Skills ownership
split 2-2 (agy and codex for agy-worker; claude-worker and the orchestrator for
codex-worker). The orchestrator could have voted the other way and closed it 3-1
without a critic, and declined to. cursor voted **agy-worker**, against the
orchestrator, and the orchestrator **adopted the critic's side** rather than
holding and escalating. The critic attached a binding rider (skills is a
distinct workplan item with distinct review, explicitly non-blocking relative to
the Gate 1 deploy, redispatched rather than folded into the delivery PR if
capacity fails) and that rider is in the workplan.

**Critic capture gotcha for the next run:** `dispatch.sh cursor ... > file`
produced a **zero-byte file** on both the first run and a retry, despite exit 0
and despite `cursor-agent` working correctly when invoked directly. The vote was
recovered from the systemd journal:
`journalctl --user -u fdry-<label>-<ts>.service -o cat`. Do not treat an empty
critic vote file as a missing vote; check the journal first. The critic also
reported that `git show` was harness-rejected under `--mode ask`, so it voted
from the four ballots rather than the six proposal and critique commits, and it
said so itself. Recorded in 009.

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

### Open, and carried to the principal on issue #2 rather than blocking

These three are in `docs/proposals/2/TLDR.md` as questions. None blocks the
build; all three want an answer before or at Gate 1.

1. **Reports family scope.** Record 007 makes report run a mutation and DEVEL
   has zero completed report instances, so Phase 1 reports is a list tool
   returning nothing and a download tool with nothing to download. The spec
   ships **report definitions listing only** and defers the rest to Phase 2.
   That reduces `docs/SPEC.md` 4.1's `reports: list/run/download` line, which is
   why it is asked rather than decided.
2. **TLS trust material.** DEVEL's certificate is self-signed and does not
   validate against the host trust store, so the honest first registration is
   per-target verification disabled. The clean answer is a mounted lab CA
   bundle, which is deployment trust material and therefore a principal
   decision. Fingerprint pinning is **not** budgeted; see record 009.
3. **The audit invariant reading.** The team reads "no tool path ships without
   its audit write" as satisfied by a durable pre-execution attempt record plus
   a typed `outcome_unknown` terminal state plus reconciliation plus
   fail-closed. All four ballots voted not to escalate, on two conditions: that
   the reading is written down in the record (done, 009 decision 7-sub) and that
   it appears in the Gate 1 packet as a named item (in the workplan). It is the
   principal's invariant and he should get to overrule the reading.

### CLOSED 2026-07-24: the DEVEL service account object scope

**Resolved by Scott, and re-verified live by this run before being treated as
resolved**, per the issue's explicit instruction not to trust the relayed
assertion:

```
GET /suite-api/api/resources?pageSize=1            -> totalCount: 517
GET /suite-api/api/adapterkinds                    -> 21 adapter kinds
GET /suite-api/api/resources?adapterKind=VMWARE    -> totalCount: 169
GET /suite-api/api/resources?adapterKind=CONTAINER -> totalCount: 52
```

The account previously saw 4 objects and zero virtual machines. Gate 1 is
meaningful again, and every payload-size and scope-control argument that the
4-object world had softened is back at full force.

**Note for the next run:** agy-worker's phase-3 ballot re-raised this blocker as
its scope check *after* the dispatch prompt gave it the 517-object measurements
at the top of the page. None of its six votes turns on the count and all six
were counted, but a seat that does not update on evidence placed in front of it
is worth watching. Recorded in 009's process note.

### Closed 2026-07-21 by the previous run

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

**Do not dispatch implementation until the principal approves
`docs/proposals/2/` on GitHub issue #2.** That approval is the gate this round
ends on. If the run wakes to an unapproved issue, there is nothing to do but
wait; do not start the build to be helpful.

On approval:

1. **Collect sign-offs on record 009** from all three doers. Protected path
   `src/vcf_ops_mcp/` is in scope, and 009 is deliberately unsigned today
   because this round authorized no code.
2. **Fold the principal's answers** to the three open questions (reports scope,
   TLS trust material, the audit invariant reading) into 009 as an amendment
   before dispatching, exactly as round 1's resolutions were folded into records
   001 and 003. If he changes the reports scope, the read plane's estimate moves
   by about a dispatch-day.
3. **Run step 0 of the workplan first: the two day-one spikes.** FastMCP
   identity injection (codex-worker) and the fleet-caddy Streamable HTTP smoke
   (agy-worker). Both are cheap and either can reorder the build. Do not skip
   them because the plan looks settled.
4. **Then `contracts.py`** as one short commit from codex-worker, the only
   planned serialization point, before the three slices fan out.
5. **Then dispatch the four slices** per record 009 decision 6: codex-worker the
   spine, claude-worker the read plane, agy-worker delivery, agy-worker skills.
   The skills piece carries the critic's binding rider: distinct workplan item,
   distinct review, non-blocking relative to the Gate 1 deploy, redispatched
   rather than folded into the delivery PR if capacity fails.
6. **Do not let CI and deploy be deferred behind admin and MCP** inside the
   delivery slice. That was the original mitigation and it defers the long pole.
7. **Non-blocking sweep items:** `tools/consensus-check.py:516` still cites
   `001-town-motion.md`, a template leftover, prose only. And codex-worker
   reported a duplicated `logs via VCF Ops).` line in `docs/SPEC.md` section 5
   that it deliberately left alone because record 008 did not authorize that
   correction. That was the right call; it needs its own authorization.
   The `src/core/` and `ARCHITECTURE.md` strings elsewhere in
   `consensus-check.py` are deliberate synthetic fixtures and must **not** be
   "fixed".

## Sweep, round 3 PR-open (2026-07-26T01:3xZ)

Run at the close of the PR-open run. **The round is not closed**: PR #3 is open
awaiting the external Codex review, so the end-of-round expectation of zero
branches does not apply yet. Everything below is retained on purpose.

- **Open team PRs: one, #3.** That is the round PR and it is the correct state.
  Green on every check. Awaiting external review.
- **Doer-prefixed branches on `origin`: zero.** Guard run, passed, after the
  round-branch push.
- **Round branch on `origin`: present, and this is correct** for the first time
  this round. It is the one sanctioned push, at PR-open time, per the brief.
- **Process and artifact tags on `origin`: zero.** Unchanged. `git ls-remote
  --tags origin` is empty.

Local branches retained on purpose:

| Branch | Why retained |
| --- | --- |
| `round/2-phase1-build` | the round PR head, squashed to one commit |
| `round/2-phase1-build-preSquash` | the full pre-squash integration history, kept until PR #3 merges so every reviewed SHA stays trivially reachable. **Delete at round close.** |
| `codex/r3-spine`, `claude/r3-readplane`, `agy/r3-delivery`, `agy/r3-skills` | the four signed slice heads; retained until PR #3 merges |
| `claude/r3-rev-spine`, `agy/r3-rev-readplane`, `codex/r3-rev-delivery`, `claude/r3-rev-skills` | the nine review markers, all merged |
| the phase-1/2/3 artifact and ballot branches | content now preserved in `docs/artifacts/round-3/`; **safe to delete at round close** |

The pre-squash tree was verified byte-identical to the squashed commit
(`git diff --stat` empty) before the push.

## Sweep, round 3 slice review (2026-07-26T00:5xZ, mid-round)

Run at the close of the slice-review run. **The round is not closed**: one slice
is integrated and three are redispatched, so the end-of-round expectation of zero
branches does not apply. Everything below is retained on purpose.

- **Open team PRs: zero.** Correct. The round PR opens after all four slices are
  signed and integrate green.
- **Doer-prefixed branches on `origin`: zero.** Guard run, passed.
- **Round branch on `origin`: absent.** Correct, still local-only.
- **Process and artifact tags on `origin`: zero.** Unchanged.
- Nothing was pushed this run at all.

Local branches added this run, all retained on purpose:

| Branch | Why retained |
| --- | --- |
| `claude/r3-rev-spine`, `agy/r3-rev-readplane`, `codex/r3-rev-delivery`, `claude/r3-rev-skills` | all seven review markers, first-round and re-review, already merged into the round branch. Reset each to the round head and reuse it plus its worktree for the next re-review. |
| `codex/r3-spine`, `claude/r3-readplane` | signed and integrated (`cc1007a`, `d509199`); retained until the round PR merges so the signed SHAs stay reachable |
| `agy/r3-delivery`, `agy/r3-skills` | **live slice work, unsigned.** Do not delete. Each has one short fix dispatch outstanding. |

Re-run at the very close of the run: open team PRs zero, doer branches on
`origin` zero (guard passed), round branch absent from `origin`, nothing pushed.
Round branch suite: 103 passed, 13 deselected, 69 subtests.

Worktrees added this run, four, all free and reusable for the re-review:
`vcf-ops-mcp-rev-claude`, `-rev-claude2`, `-rev-agy`, `-rev-codex`.

## Sweep, round 3 implementation (2026-07-26T00:2xZ, mid-round)

Run at the close of the implementation dispatch run. **The round is not
closed**: four slices are built and unreviewed, so the end-of-round expectation
of zero branches does not apply. Everything below is retained on purpose.

- **Open team PRs: zero.** Correct. The round PR opens after the slices are
  reviewed, integrated, and green.
- **Doer-prefixed branches on `origin`: zero.** Guard run, passed.
- **Round branch on `origin`: absent.** Correct, still local-only.
- **Process and artifact tags on `origin`: zero.** Unchanged.
- Nothing was pushed this run at all.

Local branches retained on purpose, added this run:

| Branch | Why retained |
| --- | --- |
| `codex/r3-contracts` | step-1 head `8806063`, cited by both review markers; already merged at `522218e` |
| `claude/r3-contracts-signoff` | both step-1 review markers; already merged at `33bca5d` |
| `codex/r3-spine`, `claude/r3-readplane`, `agy/r3-delivery`, `agy/r3-skills` | **live slice work, unreviewed and unmerged.** Do not delete. Each will be redispatched to continue. |

The earlier retained branches from the phase-3 sweep below are unchanged.

## Sweep, round 3 phase 3 (2026-07-24, mid-round)

Run at the close of the phase-3 orchestrator run. **The round is still not
closed**: it is parked waiting on the principal's approval of
`docs/proposals/2/` on issue #2, so the end-of-round expectation of zero
branches still does not apply. Every branch below is retained on purpose.

- **Open team PRs: zero.** Correct. The round PR does not open until the
  principal approves and the implementation slices integrate green. Only PR #1
  (`round/1-architecture`) has ever merged.
- **Doer-prefixed branches on `origin`: zero.** Guard run, passed.
- **Round branch on `origin`: absent.** Correct, and it stays local until the
  round PR opens.
- **Process and artifact tags on `origin`: zero.** The convention change landed;
  the 18 tags formerly on this origin are gone. Local tags remain the evidence
  store. Release `v*` tags are unaffected and none exist yet.
- **`main` merged into the round branch** at `3859e26`, taking `main`'s
  `TEAM-STATE.md` on the one conflicted file. `main` and the round branch no
  longer diverge on it.
- **Phase-3 artifacts are copied into the tree, not just referenced by SHA.**
  All four ballots and the critic vote are committed under
  `docs/proposals/2/ballots/`, so the ballot branches can be deleted at round
  close without orphaning anything a decision record cites.

Local branches retained on purpose, updated for phase 3:

| Branch | Why retained |
| --- | --- |
| `round/2-phase1-build` | the round's integration branch, holding this round's deliverable |
| `claude/p1-ballot`, `codex/p1-ballot`, `agy/p1-ballot` | phase-3 ballot heads cited by record 009; content already copied into the round branch |
| `p1-proposals` | all six phase-1/2 artifacts, tagged `artifacts/r3-p1-proposals-critiques` |
| `claude/p1-build`, `codex/p1-build`, `agy/phase1-proposal` | proposal artifact heads cited by record 009 |
| `claude/p1-critique`, `codex/p1-critique`, `agy/p1-critique` | critique artifact heads cited by record 009 |
| `agy/p1-build` | still empty and unused; safe to delete at round close |
| `codex/spec-alerts-read-only`, `agy/spec-review` | SPEC fast-lane heads, already merged at `0481ae7`; safe to delete once the round PR merges |

## End-of-run sweep, round 3 phase 2 (superseded by the sweep above)

Run at the close of the phase-2 orchestrator run. The round was **not** closed, so the
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

### From the round-3 slice-review run (2026-07-26)

- **Provision review worktrees up front and the review round is one parallel
  batch.** Four reviews ran concurrently into four fresh worktrees, each with the
  author's worktree passed as `--add-dir` so it could run tests read-only where
  the slice was checked out, and each committing its marker on its own branch cut
  from the round head. 123 to 329 seconds, no interference, no rebases. This is
  the shape; the previous run's inability to review was purely a worktree
  shortage.
- **Fix trailer defects before the review, never after.** A trailer amend
  rewrites the commit, and a marker naming the old SHA silently stops covering
  it. Both amends this run were message-only and verified with
  `git diff --stat <old> <new>` returning empty.
- **Stating the exact expected trailer string in the prompt worked first try on
  both seats**, including the seat that had produced the defect two rounds
  running. Do not describe the rule; paste the literal string.
- **Naming specific claims caught a constitution violation this time, not just a
  record defect.** Four rounds running now. The spine review's claim 1 asked for
  a step-by-step walk of SPEC section 3 rather than "does the ordering look
  right", and that is what surfaced that no denial path writes an audit row at
  all. A generic review would have seen correct-looking authorization code and
  signed it.
- **Verify a thin sign-off rather than rejecting it on reputation.** agy-worker
  signed 5506 lines in 123 seconds. Every checkable claim in its marker was
  independently confirmed by the orchestrator before the merge, and all of them
  held. Thin is a reason to check, not a reason to disbelieve, and recording the
  verification result accurately is what lets the pattern actually change.
- **Telling a reviewer the depth pattern exists, in the prompt, moved it.** The
  read-plane prompt quoted this file's own record of the seat's last two rounds,
  said an incomplete honest review was a good outcome and a fast complete-looking
  one was not, and named the one claim that had been its own finding. The result
  was still the shortest review of the round but it cited specific test functions
  and files for the first time.
- **Reviews are cheap relative to slices.** 123 to 329 seconds against caps of
  1800 to 2700. Budget generously anyway; the two long reviews were the two that
  found the most.
### From the round-3 implementation run (2026-07-25/26)

- **Poll a dispatch, never wait on it inline.** The harness Bash timeout ceiling
  is 10 minutes and every cap here is longer, so this run launched each dispatch
  with `nohup ... &` and then blocked in a separate call on
  `timeout 570 bash -c 'until <end marker exists>; do sleep 15; done'`. That is
  the shape that works. **A `timeout` that expires prints nothing and the next
  command in the chain still runs**, which looked exactly like "the dispatch
  finished" for the read plane and was not; it had 1000 seconds left. Re-check
  `systemctl --user list-units 'fdry-<label>-*'` before concluding a dispatch
  ended.
- **A review that names claims caught a real defect for the third round
  running.** The step-1 review dispatch listed seven specific claims to confirm
  or deny and said withholding was valid. claude-worker denied claim 2 and
  partially denied claim 4, and its denial was grounded in reading the installed
  SDK rather than the spike prose. Keep this framing; it is now the single
  highest-yield practice in this project.
- **Four parallel dispatches into four worktrees works cleanly.** codex, claude,
  agy, and a second agy worktree (`-r1-agy2`) ran concurrently with no
  interference. The `agy` adapter passes `--add-dir "$WORKDIR"` itself, so a
  second agy worktree needs nothing special.
- **Slice dispatches are much longer than protocol dispatches.** Protocol work
  has been 60 to 600 seconds all project. Implementation was 169s, 253s, 303s,
  and 1592s against 1800s caps. Budget 1800s or more per slice increment, and
  expect the read plane and delivery to be the long poles.
- **Peer review needs its own worktree.** A reviewer commits its marker, so it
  cannot borrow the author's worktree while the author's branch is checked out
  there. This run had no free worktree at slice-review time, which is the
  proximate reason the review round is owed to the next run rather than done.
  Provision `-rev-<resident>` worktrees up front next time.

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
