# 011: repair the post-merge deploy path (issue #4)

- **Status:** accepted
- **Date:** 2026-07-27
- **Assignment:** GitHub issue sentania-labs/vcf-ops-mcp#4, "Post-merge deploy
  fails: workflow missing permissions block, image push denied", routed by the
  GitHub-issue pipeline. Scoped in `docs/history/prompts/r4-assignment.md`
  (relocated from the now-deleted team-tracking directory; see decision
  record 015).
- **Orchestrator run:** `gh-issue-4-triage-20260727-013122`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker

This round delivered a spec and a workplan, not code. The deliverable is
`docs/proposals/4/` on `round/4-deploy-permissions` and it stays there until
the principal approves it on the issue. No PR was opened and nothing merged to
`main`.

## Context

Issue #4 reported that the post-merge Build & Deploy run fails at the image
push with `denied: installation not allowed to Create organization package`,
diagnosed the cause as a missing `permissions:` block, and asserted that this
was "the only thing between merged code and a running service." Its acceptance
criteria were a green run and a 200 from
`https://vcf-ops-mcp.int.sentania.net/healthz`.

Triage sent this to full protocol. The diff is fast-lane sized and verified
against a working sibling, but the acceptance criteria are not: the assertion
about lab state was untested, and the `deploy` job is gated
`if: github.ref == 'refs/heads/main'`, so the fix cannot be proven before it
merges. A single worker writing three lines of YAML would not have investigated
any of that. All three doers were dispatched because each had a distinct real
angle: CI security, the slot model, and the application's health contract.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/r4-deploy-permissions` | `38539598126010d605fa5a4fe251b9099b0279fa` |
| codex-worker | `codex/r4-deploy-permissions` | `c1558944b00c180d4f6489504497368cbc9b2cc0` |
| agy-worker | `agy/r4-deploy-permissions` | `996deaac2c4b3cc2e023e743abbbc4332a048c4b` |

**claude-worker** rejected the issue's framing and enumerated five defects from
read-only recon, of which four were not in the issue: the missing secrets, the
structurally unreachable `/healthz` 200, the unsupplied `SESSION_SECRET`, and
the unattested forced-command interface. It proposed workflow-level
`permissions:`, a build/deploy job split to buy a round-branch test loop, a
preflight step, the rename, and a two-slice scope split.

**codex-worker** proposed the minimal repair with job-scoped `permissions:`,
independently found the missing secrets, deferred the rename, and converted
every other unknown into a named pre-merge gate. Its central argument was that
attribution of the next failure is the scarce resource and every unrelated line
in the diff spends it.

**agy-worker** proposed job-scoped `permissions:` plus an
`org.opencontainers.image.source` label and the rename, and put its analytical
effort into predicting where the run would die. It predicted a private-package
pull failure remediated by a manual visibility flip.

## Critiques (phase 2, adversarial)

| Worker | Critique commit SHA |
| --- | --- |
| claude-worker | `a7b740c6841ece359bfe30bcea83a9431bf61aac` |
| codex-worker | `6f341a11a59a2714b3d5966c42e3b26136a8ca58` |
| agy-worker | `5f52789381b0fe31ae624fe640d8069e427f15f0` |

The round was not a "looks good" round. Every proposal took substantive damage,
including the strongest one, and two residents conceded central positions.

**The permissions question was settled by a value, not a principle.** The
critique round was told to read `default_workflow_permissions` rather than
argue from least-privilege in the abstract. It is `read`. That killed
claude-worker's argument that a workflow-level block is a net token reduction
for the `test` job: the `test` job is already read-only, so a workflow-level
`packages: write` would widen it. claude-worker withdrew the conclusion and,
notably, withdrew its supporting evidence too: it had cited hearthgate's
workflow-level block without noting that `build.yml` contains a single job, so
its workflow level and job level are the same set, while hearthgate's other
workflow drops to `packages: read`. The sibling's actual practice is
scope-per-workload, which is evidence for codex-worker's placement. That
self-correction is recorded here because a reviewer trusting the original
citation would have been led wrong.

**codex-worker's own pre-merge gate was shown to be unsatisfiable.** Its phase-1
step 3 required a local `/healthz` 200 before merge. claude-worker showed that
200 is unreachable at any digest, so the gate had exactly two outcomes: block
the round forever, or get quietly waived with its authority still claimed.
codex-worker conceded in its critique: "I was wrong in my phase-1 proposal to
describe a synthetic local `/healthz` 200 as a pre-merge gate." The replacement
is a local run whose expected result is documented as a 503, which proves the
image builds, starts, and binds, and which can actually pass.

**agy-worker's headline risk was refuted by measurement.** It named a private
package pull failure as the primary break point with a manual visibility flip
as the remediation. An anonymous GHCR token probe shows hearthgate's package is
private while a known-public control mints a token, and hearthgate's
`deploy.yml` pulls that private package with no registry login step anywhere,
so the docker.int host holds a daemon-level credential. Private is the working
convention on this host. agy-worker's proposal also left
`secrets.DOCKER_INT_DEPLOY_KEY` untouched, so its entire post-merge runbook was
built on a step that dies at an ssh to a host literally named `deploy@` before
the pull it predicted ever happens. codex-worker and claude-worker both landed
this independently.

**A constitution point was raised and is recorded as resolved.** claude-worker
flagged agy-worker's "less than 10 minutes to write the commit and merge the
PR" as violating the no-self-merge rule in `CLAUDE.md`. The orchestrator reads
this as loose phrasing rather than intent, and agy-worker did not act on it.
The substantive half of the objection stands: an estimate that counts only
typing and omits peer review, sign-off, integration, and external review is not
conservative by accident.

**The orchestrator independently verified the load-bearing claims** rather than
taking them: the repo default workflow permissions value, the repository and
organization secret and variable inventories, the absence of branch protection,
`app.py`'s 503 path and `SESSION_SECRET` raise, the absence of any concrete
`AuditRepository` in `src/`, the absence of a compose file, the anonymous GHCR
token responses for hearthgate and a public control, and hearthgate's
`deploy.yml` running arbitrary `scp` and `docker compose` commands with no
registry login. All confirmed as reported.

## Ballots (four ballots, per the contested-synthesis rule)

Two questions remained contested after phase 2 and went to four ballots. The
other converged points (job-scoped permissions 3-0, preflight, the scope split,
the conditional deploy-key rename) were not balloted.

Question A was re-balloted rather than counted from the critiques because its
terms changed: claude-worker dropped the `needs.build.outputs.digest` mechanism
both peers had attacked, in favor of deploying the immutable
`:${{ github.sha }}` tag the build already pushes. The peers had critiqued a
proposal that no longer existed.

| Worker | Ballot commit SHA |
| --- | --- |
| claude-worker | `88bc5f969631562a2d212f8baf18e78b938ce767` |
| codex-worker | `b71f8b5626135f717217f688323e616b7f6785fe` |
| agy-worker | `4867de401ded64693392931b8ce62cf89d2f38de` |

### Question A: split the `deploy` job into `build` and `deploy`?

| Ballot | Vote | Interest |
| --- | --- | --- |
| claude-worker | for | proposed the split, dropped the attacked mechanism |
| codex-worker | for | argued against the earlier split mechanism |
| agy-worker | for | none declared |
| orchestrator | for | none |

**4-0 for. Decided without the critic.**

Orchestrator's reasoning, recorded as a ballot rather than as a ruling: the
premise codex-worker was optimizing against, that the build can only be
exercised on `main`, is verifiably false. The workflow already triggers on
`push: branches: [main, "round/*"]` and only the `deploy` job's ref gate stops
anything from running there, and the sibling this repo copies already builds
and pushes from `round/*`. The scarcity was self-imposed. Dropping the
cross-job output boundary in favor of the `:${{ github.sha }}` tag removes the
one genuinely untestable piece, which is what turned codex-worker's vote. The
remaining cost, publishing images built from unreviewed code, is real and is
a policy question rather than a testability one, so it goes up as Decision 4
with a stated fallback.

All four ballots agree round-branch publication should be a numbered decision
the principal can veto. agy-worker's fallback differs from the other three and
is recorded: it would "restrict the push to `main` and leave the build-only
step running on round branches", whereas claude-worker and codex-worker would
revert to a single `deploy` job. The orchestrator adopts the claude/codex
fallback because agy-worker's variant leaves a job that builds without pushing,
which proves the build compiles but not the thing the round cares about, which
is the permission on the push.

### Question B: rename `ai-log-depot.yml` to `vcf-ops-mcp.yml` this round?

| Ballot | Vote | Interest |
| --- | --- | --- |
| claude-worker | for, standalone-commit form | not a party |
| agy-worker | for | proposed the rename |
| orchestrator | for | none |
| codex-worker | **against** | argued to defer the rename |

**3-1 for. Decided without the critic.**

Orchestrator's reasoning: three independent recons agree nothing
machine-readable consumes the file name or the check-run name, and the
orchestrator confirmed `404 Branch not protected` itself. codex-worker's
principle (do not add an unrelated variable while diagnosing a path that has
never run) is a good one, but a variable is only a variable if it can affect
the outcome, and this one has been positively established not to. The
standalone-commit ordering answers the git-history half of the attribution
objection completely. The window argument is what tips it: `main` is
unprotected today, so no ruleset pins a check name, and the first time someone
adds required status checks the rename acquires a cost it does not have now.

**codex-worker's dissent, verbatim:**

> **Vote: against, regardless of Question A.** A standalone rename commit answers
> the attribution objection, but it does not preserve Actions run continuity or
> reduce the operational variables during the first deployment repair. The stale
> name should be corrected in a later housekeeping change after deployment is
> proven. I previously argued to defer the rename.

The Actions-run-continuity half of that objection is not answered by anything
in the synthesis, and the orchestrator concedes it: the Actions UI groups runs
by workflow file, so the existing history stops grouping with the renamed file.
The ruling is that for a workflow whose entire history is one green test job
and one failed deploy, that loss is small. If codex-worker is right that
operational continuity matters more than it looks, the cost is paid at exactly
one moment and is recoverable by reading the old workflow's history under its
old name.

## Decision

The converged change and the reasoning are in `docs/proposals/4/SPEC.md`. The
execution order and the capability-based division of labor are in
`docs/proposals/4/WORKPLAN.md`. In summary:

1. `permissions: {contents: read, packages: write}` on the package-pushing job
   only, not at workflow level.
2. Split `deploy` into `build` and `deploy`; deploy the immutable
   `:${{ github.sha }}` tag rather than passing a digest across jobs.
3. A preflight step that fails loudly on missing deploy inputs without printing
   values.
4. Correct the deploy inputs: `DOCKER_DEPLOY_KEY`, and `DOCKER_DEPLOY_HOST` /
   `SERVICE_URL` as repository variables rather than secrets, conditional on the
   principal's confirmation of key identity and value shape.
5. Rename the workflow and file, in a standalone commit ordered first.
6. Split the round: Slice A is the workflow, Slice B is the application
   (`SESSION_SECRET` and a concrete `AuditRepository`). Acceptance criterion two
   is not reachable by Slice A and the issue says so rather than closing
   silently.

Five decisions go to the principal, each with a default and the consequence of
no approval. They are enumerated in `SPEC.md` section 4. Package visibility is
deliberately not among them, because the measurement says the default action is
a read-only credential-scope confirmation.

## Division of labor

**codex-worker owns Slice A**, the workflow file, with **agy-worker** reviewing.
**agy-worker owns the two read-only attestations** in workplan steps 1 and 2,
where its slot-model ownership is genuinely load-bearing. **claude-worker owns
Slice B** when it is filed, with codex-worker reviewing.

claude-worker wrote the round's strongest proposal and gets no part of Slice A.
It said so itself, correctly: "I am not the right owner for the workflow
file... Splitting a three-line YAML diff across three doers would be theater."
This is a normal outcome of capability-based division, not a slight, and it is
recorded here so a later reader does not misread it as one.



## Notes on protected paths and integration

`.github/workflows/` is not in `.github/protected-paths.txt`, so Slice A needs
no decision record on protected-path grounds. This record exists because the
round is a consensus spec, not because a gate demanded it.

The three doer branches carried only authored artifacts (proposal, critique,
ballot), no code and no shared files, so they were integrated into the round
branch without pre-integration peer sign-off markers. That follows the round-1
precedent, where doers ratified the decision records rather than signing each
other's proposal documents. The sign-off gate applies in full to Slice A's
implementation.

## Sign-offs

Signatures in the format `tools/consensus-check.py` reads, following the
shape of `009-phase1-build-synthesis.md`. Each doer appended only its own
line, on its own branch; the orchestrator collected them here at merge and
changed no line's content. The longer per-doer ratification write-ups for
011 remain under `docs/decisions/signatures/`.

    Signed-off-by: claude-worker <claude@team.local> 2026-07-27T11:58:46Z
    Signed-off-by: codex-worker <codex@team.local> 2026-07-27T11:58:30Z
    Signed-off-by: agy-worker <agy@team.local> 2026-07-27T11:58:16Z
