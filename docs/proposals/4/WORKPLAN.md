# Round 4 workplan: Slice A, the deploy path

Read `SPEC.md` first. This is the execution order for Slice A only, assuming
Decisions 1 through 4 are approved. Slice B is scoped in `SPEC.md` section 3
and is not planned here.

The ordering principle: every step before step 6 is reversible and none of them
touches `main`. The scarce resource is not the merge, it is the attribution of
the next failure, and each step below is designed to fail in exactly one place.

## Division of labor

Assigned by capability, per the phase-3 rule, not by fairness. All three doers
claimed honestly and two of them said out loud that the file should have one
owner rather than three, which is correct.

| Piece | Owner | Reviewer | Why |
| --- | --- | --- | --- |
| Slice A, the workflow file | **codex-worker** | agy-worker | It prescribed the round-3 deploy-key design that survived three withheld sign-offs, it argued the winning least-privilege placement, it was the only resident to propose a mechanical constitution check on the diff, and its instinct throughout this round was to keep the repair narrow and attributable. That is the right instinct for a file that has never successfully run. |
| Runbook steps 1 and 2, the read-only attestations | **agy-worker** | n/a, no code | It owns the slot model and is the natural interface to the lab-admin questions in Decisions 2 and 3. This is where its ownership claim is genuinely load-bearing. |
| Slice B, when filed | **claude-worker** | codex-worker | It found D3 and D4 from source rather than from the issue, it built the healthz reasoning in round 3, and the `SESSION_SECRET` persistence design is its proposal. |

claude-worker gets no part of Slice A despite writing the round's strongest
proposal, and it said so itself: "I am not the right owner for the workflow
file... Splitting a three-line YAML diff across three doers would be theater."
That is the correct call and it is recorded as a normal outcome, not a slight.
It reviews nothing in Slice A either, because two non-authors is one more than
the gate needs and codex-worker's diff is small.

## Step 0. Prerequisites, before any code

Blocking. Nothing in Slice A starts until these land.

- Decision 1 approved (scope split) and the Slice B issue filed.
- Decision 2 answered: `DOCKER_DEPLOY_KEY` confirmed as this slot's key, and
  `DOCKER_DEPLOY_HOST` plus `SERVICE_URL` created as repository variables.
  **Specify the shape when you create them.** `DOCKER_DEPLOY_HOST` must be
  either a bare hostname (the workflow supplies `deploy@`) or a full
  `user@host` (the workflow drops its hardcoded prefix). Say which; the
  preflight cannot catch a wrong-shaped non-empty value.
- Decision 4 answered (round-branch publication). A veto changes step 3 and
  step 5, not the rest.

## Step 1. Attest the slot contract. Read-only. agy-worker.

Ask lab-admin, without ssh: does the forced command behind the `vcf-ops-mcp`
slot key accept `get-digest` and a bare image reference, or is it a
hearthgate-shaped general shell key.

*Proves:* D5, the round's largest unattested assumption.
*Failure signal:* the answer is "general shell key". Then Slice A stops being a
workflow repair and becomes a deploy redesign around a compose file and a slot
volume layout, and it goes back to the principal before anyone writes YAML.
*Blocking for:* the deploy half of the file. Blocking for nothing else.

## Step 2. Confirm the host's GHCR credential covers the new package. Read-only. agy-worker.

The docker.int host pulls hearthgate's private package with no
workflow-supplied credential, so it holds a daemon-level GHCR credential. Ask
whether that credential is org-scoped, in which case
`ghcr.io/sentania-labs/vcf-ops-mcp` is already pullable and there is nothing to
do.

*Proves:* that a green push actually yields a pullable image, which is the
failure mode where criterion one passes and criterion two fails anyway.
*Failure signal:* the credential is per-package. Then a credential scope change
or a package visibility decision goes to the principal (see `SPEC.md` D6), and
it is a decision, not a mid-run button click.

## Step 3. Commit Slice A to `codex/r4-deploy-permissions`. codex-worker.

Two commits, per `SPEC.md` section 2: the rename alone, then the substance.
**Commit to the doer branch. Do not push, and do not commit to the round
branch.** Doers never push; the orchestrator integrates after sign-off.

*Failure signal:* none available yet, by construction. Nothing runs on a
`codex/*` branch, because the workflow triggers only on
`push: branches: [main, "round/*"]`. The proof arrives in step 6.

## Step 4. Static check of the diff before review. codex-worker.

Parse the YAML, confirm the diff changes only what `SPEC.md` section 2 names,
and scan it for an em-dash and for anything resembling a secret value. This is
the one mechanical constitution check the round produced and it belongs in
every future workflow slice.

*Failure signal:* any of the four. Each stops the branch, not the merge.

## Step 5. Peer sign-off. agy-worker reviews.

Standard gate. `.team/signoffs/` marker naming the exact commit, written by a
non-author. No marker, no integration. Do not rebase a signed branch.

## Step 6. Integrate to the round branch, and read the result back. Orchestrator merges, agy-worker reads.

The orchestrator merges the signed commit into
`round/4-deploy-permissions` and pushes it. **This is the step that produces
the round's actual proof**, because it is the first moment anything Slice A
wrote is on a ref the workflow triggers on.

*Proves:* D1. The GHCR push succeeds and the package is created, before the
merge to `main` and without spending it.
*Failure signal:* still `denied: installation not allowed to Create
organization package`. That would mean the cause is an org setting after all,
hearthgate notwithstanding, and the round escalates rather than guessing. A
different `denied:` string gets read literally, not pattern-matched to D1.

Then read the package back: `gh api
orgs/sentania-labs/packages/container/vcf-ops-mcp` with a token carrying
`read:packages`, checking `visibility` and `repository`. Note that the
orchestrator's token lacks that scope, so this needs one that has it.

*Proves:* what the first push actually produced, including whether repo linkage
happened.
*Failure signal:* private with no repo linkage, combined with a step-2 answer of
"per-package credential". That combination requires a decision before the merge
rather than after.

*If Decision 4 was vetoed:* the build/deploy split comes out of the diff, this
step proves nothing, and the first real exercise moves to step 7.

## Step 7. Merge to `main`. One shot, and by now a much smaller one.

**Read this before watching the run. Under Slice A alone, step 7 is expected to
end red at the health poll**, because `/healthz` returns 503 by construction
(D3, D4). This is not a surprise to be debugged and it is not a timeout to be
extended. The run is green through the push and the slot deploy, and the health
gate is Slice B's acceptance test arriving early. Whoever watches the run needs
to know that beforehand, because treating a permanent structural 503 as a
transient timing problem is the most expensive misdiagnosis this round can hand
off, and the natural response to it (extend the timeout, re-run) burns a merge.

*Proves:* criterion one end to end.
*Failure signals, each distinguishable from the others by design:*
- Preflight fails naming a variable: step 0 was not done.
- First ssh fails: D5 landed on the bad side despite step 1.
- Health poll exhausts 12 tries: expected if Slice B has not landed. The
  rollback then tries `PREV_DIGEST`, which on a first-ever deploy is `none`,
  and correctly logs "No prior digest found to roll back to" before exiting 1.
  That path is at least written correctly.

If that red run is unacceptable as an end state for #4, the alternative is to
land Slice B first and merge them together, which trades a clean run for a
week. The team recommends shipping Slice A and saying plainly on the issue what
the health gate is doing.

## Step 8. Evidence for the closing comment.

- The `main` run link and the commit SHA.
- The image digest, and the package's visibility and repository linkage from
  step 5.
- `curl -i https://vcf-ops-mcp.int.sentania.net/healthz` output, verbatim,
  including if it is a 503, with the reason and a pointer to the Slice B issue.
- The step-1 answer, recorded, because it is the durable fact this repo did not
  previously have written down anywhere.
- A line stating that `TEAM-STATE.md:321` overstated the round-3 secret work and
  that the missing configuration was created in step 0.

A closing comment that says "added three lines, it works" when five things were
wrong teaches the next round nothing, and this repo has already paid once for
exactly that.

## Follow-ups this round deliberately does not do

Recorded so they are not lost, in the order they are worth doing.

1. **The deploy shell's rough edges**, all of which are real and none of which
   belong in the same commit as the repair: `StrictHostKeyChecking=no` where
   `accept-new` would do, unquoted `$DEPLOY_HOST` and `$SERVICE_URL`
   expansions, `curl -k` against a host whose TLS is now known good, the
   60-second health budget, and `get-digest || echo "none"` discarding the one
   diagnostic signal the step has.
2. **The `BaseException` lease leak** in the dispatcher, carried from round 3.
   Finalization is keyed on `except asyncio.CancelledError` rather than
   `except BaseException`. A few lines, fast-lane sized.
3. **`bin/team-provenance-ledger` writes an em-dash.** Belongs to whoever next
   touches the framework, not to this project.
4. **Close `.team/blocked/fleet-caddy-slot-config.md`.** It is resolved and it
   reads as open.
5. **The Dockerfile builds wheels for a hardcoded dependency list** at line 13
   rather than resolving from `pyproject.toml`, so the installed set may not
   match what the tests run against.
6. **`main` has no branch protection**, so the consensus gate and CI are both
   advisory. Worth a deliberate decision rather than an accident.
