# Round 4 proposal, claude-worker

Issue: sentania-labs/vcf-mcp#4, "Post-merge deploy fails: workflow missing
permissions block, image push denied". Round branch `round/4-deploy-permissions`.

This round ships a spec and a workplan, not the fix. Nothing here was applied.
`.github/workflows/ai-log-depot.yml` is unmodified in my worktree.

## Headline

The issue's three-line diff is correct and I would apply it verbatim. Its
framing is not: "this permissions gap is the only thing between merged code
and a running service" is false, and I can show it from read-only recon
without merging anything.

Five defects sit between `main` today and a 200 from
`https://vcf-mcp.int.sentania.net/healthz`. Only the first is the one the
issue names. Two of the remaining four are in the workflow, two are in the
application, and the application pair means acceptance criterion two is not
one merge away at all: it depends on a component this repo has never built.

I also want the round to stop treating "one shot on `main`" as a law of
nature. It is a line of YAML. Most of what is untested here can be tested on a
round branch before the merge, and buying that test loop back is the single
highest-value thing this round can do.

## 1. Approach

### 1.1 What recon established

Every claim below is from read-only calls. No org, repo, package, or lab-host
state was changed. No `gh api -X POST/PATCH/PUT/DELETE`, no ssh.

**D1. Missing `permissions:`. CONFIRMED, and the issue's diagnosis is right.**

`gh run view 30184249021` shows `CI Pipeline` green in 26s, `Build & Deploy`
failing in 34s at `Build and push image`, annotation:

```
buildx failed with: ERROR: failed to build: failed to solve: failed to push
ghcr.io/sentania-labs/vcf-mcp:7cb9d053999aff1f10558c331327f1fe35f3a525:
denied: installation not allowed to Create organization package
```

`Login to GitHub Container Registry` passed. The token authenticated and was
refused the create. That is the `packages: write` signature.

**D2. Three of the four secrets the deploy step reads do not exist. CONFIRMED,
and this one is fatal on its own.**

```
gh api repos/sentania-labs/vcf-mcp/actions/secrets   -> DOCKER_DEPLOY_KEY (only)
gh api repos/.../actions/variables                       -> total_count: 0
gh api repos/.../actions/organization-secrets            -> AWS_*, DNS_SERVER,
                                                            DOCKER_HUB_*, KRB*,
                                                            REPO_ACCESS_TOKEN
gh api repos/.../actions/organization-variables          -> VCFA_URL
```

The workflow reads `secrets.DOCKER_INT_DEPLOY_KEY`, `secrets.DEPLOY_HOST`, and
`secrets.SERVICE_URL`. None of the three exists at repo or org level. The one
secret that does exist is named `DOCKER_DEPLOY_KEY`, matching hearthgate's
name, created 2026-07-20, and the workflow does not read it.

So on the first run that gets past the push, the step writes an empty file to
`$KEY_PATH`, runs `ssh -i <empty key> deploy@ vcf-mcp get-digest` (host
literally `deploy@`), swallows that failure through `|| echo "none"`, and then
runs the second `ssh` with no `||` guard. GitHub runs `run:` blocks under
`bash -e`, so the step exits nonzero there. Criterion one, "slot deploy
executed", fails on the very next attempt after D1 is fixed.

This also contradicts the durable state file. `TEAM-STATE.md:321` records that
"the lab FQDNs are out of the workflow and into `DEPLOY_HOST` / `SERVICE_URL`
Actions secrets". The FQDNs did come out of the workflow. The secrets were
never created. The round-3 sign-off closed that item on the diff, which is all
a diff can show, and nobody checked the other half. That is worth a line in
the closing comment on its own.

**D3. `/healthz` cannot return 200 from the container image, at any digest.
CONFIRMED, and it is already a known open finding.**

`Dockerfile:38` starts `uvicorn vcf_mcp.app:create_app --factory`. Uvicorn
calls the factory with no arguments, so `audit_repository` takes its default of
`None` (`app.py:54`). `healthz` then falls to the `else` branch at
`app.py:27-34` and returns 503 unconditionally. There is no path through the
production entry point that reaches the 200.

Wiring one is not a small edit, because there is nothing to wire.
`AuditRepository` (`contracts.py:256`) is a `Protocol`. `grep -rl AuditRepository src/`
returns only `contracts.py`, `app.py`, and `dispatcher/core.py`; there is no
concrete implementation, and `grep -rl 'sqlite\|aiosqlite' src/ tests/` returns
nothing. The only implementations are in-memory mocks under `tests/`.

codex-worker already found and denied this in round 3
(`.team/signoffs/agy-r3-delivery-19efb0cdab60.md`, claim 4: "wire the concrete
durable repository in the application factory"). It was recorded as
PARTIALLY CLOSED and carried forward. Issue #4 does not know about it.

**D4. The container raises at startup before it ever binds. CONFIRMED.**

`app.py:57-59` raises `RuntimeError` when `SESSION_SECRET` is unset. That
fail-closed behavior is correct and was a round-3 review requirement. But
nothing supplies the value: there is no compose file anywhere in the repo
(`find . -name 'compose*.y*ml' -o -name 'docker-compose*'` is empty, despite
`docs/SPEC.md:66` describing "one container image (plus compose file)"), the
deploy interface passes only an image reference, and the workflow sets no
container environment. The factory raises, uvicorn exits nonzero, the slot has
no listener, and fleet-caddy keeps returning 503.

D3 and D4 stack. Fixing D4 alone gets a live process that answers 503 on
`/healthz`. Fixing both is what criterion two actually requires.

**D5. The slot's forced-command interface is an assumption, not a verified
contract. UNRESOLVED, and it is my one-hour question.**

The deploy step calls `vcf-mcp get-digest` and `vcf-mcp <image-ref>` as
forced-command subcommands. `grep -rn 'get-digest' docs/ .team/` finds that
string nowhere outside this repo's own workflow. The nearest thing to a source
is `docs/proposals/2/SPEC.md:488`, which says "the onboarded slot's
forced-command key" and names no verbs. The verbs were invented here.

The working sibling does it differently. `sentania-labs/hearthgate`
`deploy.yml` scp's a compose file to the host and then runs three plain
`ssh ... "docker compose ... pull|up -d|ps"` commands against
`vars.DOCKER_DEPLOY_HOST`. That is a general-purpose shell key, not a forced
command with a subcommand grammar. If docker.int onboarded this project the
same way lab-admin onboarded hearthgate, `vcf-mcp get-digest` is not a
thing the key can run, and the entire deploy step is written against an
interface that does not exist.

I cannot settle this without ssh, which recon rules out. It is the single
biggest unknown in the round and I say so rather than hedging past it.

### 1.2 What I can rule out, with evidence

**The rename is free. Do it.** Three named worries, all of them empty:

- Branch protection: `gh api repos/sentania-labs/vcf-mcp/branches/main/protection`
  returns `404 Branch not protected`. There are no required status checks to
  break. (Separately: that means the consensus gate and CI are both
  advisory on `main` right now, which someone should want to know.)
- `consensus.yml`: I read it in full. It references no other workflow, no
  check-run name, and nothing about the deploy job.
- Everything else that mentions `ai-log-depot` is prose in `TEAM-STATE.md`,
  `docs/`, and `.team/`. No machinery reads it.

Renaming the file changes the check-run name from `ai-log-depot / Build & Deploy`
to `vcf-mcp / Build & Deploy`. Nothing consumes either string. The only
real cost is that the old run history no longer groups with the new file in the
Actions sidebar, which for a workflow with one failing run is not a cost.

**Org policy is not blocking package creation.** hearthgate pushes to
`ghcr.io/sentania-labs/hearthgate` from the same org with exactly
`permissions: {contents: read, packages: write}` at workflow level and nothing
else. If the org restricted container creation, hearthgate would fail the same
way. It does not. The `installation not allowed` wording points at the
workflow token's own permission set, not at an org setting.

**fleet-caddy is genuinely resolved.**
`curl -s -o /dev/null -w '%{http_code}' https://vcf-mcp.int.sentania.net/healthz`
returns `503` today. During round 3's spike 002 the same host died at Client
Hello with `SSL_ERROR_SYSCALL` (`.team/blocked/fleet-caddy-slot-config.md`).
TLS now terminates and the proxy answers, so the per-slot config landed as the
issue says. `.team/blocked/fleet-caddy-slot-config.md` should be closed out
this round, since it is still sitting there reading as open.

**The package does not exist yet.**
`gh api orgs/sentania-labs/packages/container/vcf-mcp` returns
`404 Package not found`, while the same call for `hearthgate` returns a
`403 read:packages scope` error from the same token. The token's scopes
(`gist, read:org, repo, workflow`) lack `read:packages` in both cases, so the
404-before-403 ordering is suggestive rather than conclusive, and I will not
claim more than that. It is consistent with the push having never succeeded,
which the run log independently confirms. Practically: the first successful
push is a create, and creates land private.

### 1.3 The diff I would apply

Two commits, both in `.github/workflows/`, one file.

**Commit 1, `vcf-mcp.yml` (git mv from `ai-log-depot.yml`).** The rename
alone, so the substantive diff in commit 2 is readable rather than buried in a
whole-file add/delete pair.

```yaml
-name: ai-log-depot
+name: vcf-mcp
```

**Commit 2, the substance.**

```yaml
 name: vcf-mcp

+permissions:
+  contents: read
+  packages: write
+
 on:
   push:
     branches: [ "main", "round/*" ]
   pull_request:
     branches: [ "main" ]
```

Then split the current `deploy` job in two:

```yaml
   build:
     name: Build & Push
     needs: test
     runs-on: [self-hosted]
     if: github.repository == 'sentania-labs/vcf-mcp'
     outputs:
       digest: ${{ steps.build.outputs.digest }}
     steps:
       # checkout, buildx, ghcr login unchanged
       - name: Build and push image
         id: build
         uses: docker/build-push-action@v5
         with:
           context: .
           push: true
           tags: ghcr.io/sentania-labs/vcf-mcp:${{ github.sha }}

   deploy:
     name: Build & Deploy
     needs: build
     runs-on: [self-hosted]
     if: github.ref == 'refs/heads/main' && github.repository == 'sentania-labs/vcf-mcp'
     steps:
       - name: Preflight, required deploy configuration is present
         env:
           DEPLOY_KEY: ${{ secrets.DOCKER_DEPLOY_KEY }}
           DEPLOY_HOST: ${{ secrets.DEPLOY_HOST }}
           SERVICE_URL: ${{ secrets.SERVICE_URL }}
         run: |
           missing=""
           [ -n "$DEPLOY_KEY" ]  || missing="$missing DOCKER_DEPLOY_KEY"
           [ -n "$DEPLOY_HOST" ] || missing="$missing DEPLOY_HOST"
           [ -n "$SERVICE_URL" ] || missing="$missing SERVICE_URL"
           if [ -n "$missing" ]; then
             echo "Missing required Actions secrets:$missing" >&2
             echo "Set them in repo settings before this job can deploy." >&2
             exit 1
           fi
       # ... existing deploy step, with DOCKER_INT_DEPLOY_KEY corrected to
       #     DOCKER_DEPLOY_KEY and IMAGE_DIGEST from needs.build.outputs.digest
```

Three deliberate choices, with the arguments rather than the reflex.

**`permissions:` at workflow level, not scoped to the job.** The reflex answer
is job level, on least-privilege grounds. I think workflow level is right here
and the least-privilege argument is weaker than it looks. Declaring
`permissions:` at workflow level does not widen anything: the moment the block
appears, every job's token drops from the repo default to exactly
`contents: read, packages: write`, including the `test` job, which today runs
on whatever the repo default is. So the workflow-level block is a net
*reduction* for `test`, not an expansion. Scoping it to `deploy` only would
leave `test` on the default set, which is the more permissive outcome.

The counter is that `test` does not need `packages: write` and should not have
it. That is real but small: `test` runs on the same self-hosted runner as the
job that does need it, in the same repo, on the same commit. If an attacker
controls `test`, they control the runner, and the token scope is not what saved
you. Weigh that against matching hearthgate exactly, which makes the two repos
diffable and makes "copy the working pattern" true rather than approximate. I
take the hearthgate pattern. If the reviewer prefers per-job, I will not fight
it, but then `test` needs an explicit `permissions: {contents: read}` too, or
the change makes the repo less safe than it looks.

**Split `build` from `deploy`.** This is the part I most want to argue for,
because it is what converts "one shot on `main` per attempt" into "as many
shots as we want, then one shot on the part that genuinely cannot be tested".

Today `deploy` is gated `if: github.ref == 'refs/heads/main'` and does both the
push and the ssh. The workflow already triggers on `push: branches: [main,
"round/*"]`, so the build half can run on the round branch under exactly the
main-branch conditions: same runner, same token, same permissions block, same
registry, same image name. That proves D1's fix, proves the package gets
created, and reveals its resulting visibility and repo linkage, all before the
merge and all without touching `main`.

The objection is that this pushes image versions built from unreviewed round
branches into GHCR. In a personal-lab private package tagged by commit SHA,
with `main` deploying by digest, I read that as acceptable and cheaper than
finding out on `main`. If the team disagrees, the narrower variant is
`push: ${{ github.ref == 'refs/heads/main' }}` plus a one-off round-branch run
with it flipped, which proves the same thing once and then reverts. I prefer
the durable split, because the value is not the one-off proof; it is that every
future round can test its build without spending a merge.

**A preflight step that fails loudly.** D2 is three silent empty strings today.
The preflight turns them into one line naming exactly what is missing, before
any ssh runs. It costs eight lines and it is the difference between a
five-minute fix and a debugging session against a forced command nobody has
documented.

### 1.4 Verification, in order, with the failure signal for each step

The point of this ordering is that every step before step 5 is reversible and
none of them touches `main`.

**Step 0. Create the missing secrets.** `DEPLOY_HOST` and `SERVICE_URL` in repo
Actions secrets. Scott or the orchestrator does this; the values are lab
identifiers and never enter the repo, a commit, or transcript output. Also
settle D5 with lab-admin: what forced command is behind `DOCKER_DEPLOY_KEY`,
and does it accept `get-digest` and a bare image reference.
*Proves:* the deploy step's inputs exist and its interface is real.
*Failure signal:* lab-admin says the key is a general shell key like
hearthgate's. Then the deploy step is rewritten to the hearthgate shape (scp a
compose file, `docker compose pull && up -d`), which is a larger change than
this round has scoped, and the workplan branches here.
*This step is blocking for the deploy half and blocking for nothing else.*

**Step 1. Push the fix to `round/4-deploy-permissions`.**
*Proves:* D1. The GHCR push succeeds with `packages: write` and the package is
created.
*Failure signal:* still `denied: installation not allowed to Create
organization package`. That would mean the cause is an org setting after all,
hearthgate notwithstanding, and the round escalates to Scott rather than
guessing. A different `denied:` string means something else again and gets read
literally, not pattern-matched to D1.

**Step 2. Read the package back.**
`gh api orgs/sentania-labs/packages/container/vcf-mcp` with a token that
carries `read:packages`, checking `visibility` and `repository`. The token in
this worktree does not have that scope, so this needs a token that does.
*Proves:* what the first push actually produced, which is the orchestrator's
first named thread.
*Failure signal:* `visibility: private` with no repo linkage. Then the slot
host cannot pull unless it already holds a GHCR credential. hearthgate's
`deploy.yml` runs `docker compose pull` over ssh with no registry login step in
the workflow at all, which means either the docker.int host is already logged
in to GHCR at the daemon level or hearthgate's package is public. Determining
which decides whether this round needs a package visibility change (an org
state change, so Scott's call, not the team's) or nothing.

**Step 3. Prove the container actually starts, locally.**
`docker run` the pushed digest on a developer machine with `/data /keys /audit`
mounted, and curl `:8000/healthz`.
*Proves:* D3 and D4, before they cost a merge. Nobody has ever run this image.
*Failure signal:* container exits immediately with the `SESSION_SECRET`
`RuntimeError` (D4), or comes up and answers 503 (D3). Both are expected on
today's `main`, and both are the app-side slice's acceptance test.

**Step 4. Prove the slot can pull, without deploying.** `docker pull` the
digest on docker.int. Read-only in the "does not change service state" sense,
but it is still a command on a lab host, so it needs Scott or lab-admin to run
it, not a doer, and not this round if that is uncomfortable.
*Proves:* step 2's finding is not just theoretical. A green push followed by
`ImagePullBackOff` on the slot satisfies criterion one and fails criterion two,
which is exactly the failure mode the orchestrator flagged.
*Failure signal:* `denied` or `unauthorized` on pull. Then step 2's remediation
is required before the merge, not after.

**Step 5. Merge the round PR to `main`.** One shot, and by now the only
untested things left are the ssh interface (settled in step 0, or explicitly
accepted as a risk) and the healthz poll against a real slot.
*Proves:* criterion one end to end.
*Failure signal:* the preflight step failing means step 0 was not done. The
first ssh failing means D5 landed on the bad side. The healthz poll timing out
after 12 tries means the app-side slice did not land or the slot is not
reachable at `SERVICE_URL`, and the rollback then tries to redeploy
`PREV_DIGEST`, which on a first-ever deploy is `none` and correctly logs "No
prior digest found to roll back to" before exiting 1. That path is at least
written correctly.

**Step 6. Evidence for the closing comment.** The run link, the
`curl -i https://vcf-mcp.int.sentania.net/healthz` output showing 200 and
the JSON body, and the package visibility from step 2. Plus, and I would insist
on this, a note that `TEAM-STATE.md:321` overstated the secret work and that
the two missing secrets were created in step 0. A closing comment that says
"added three lines, it works" when five things were wrong teaches the next
round nothing.

### 1.5 What this means for scope

Criterion two ("healthz returns 200") is not reachable by any change to
`.github/workflows/`. It needs D3 and D4 fixed in `src/`, and D3 needs a
concrete `AuditRepository` that does not exist. That is a real slice of work,
not a line.

I recommend the round splits into two slices and says so plainly on the issue
rather than quietly shipping half:

- **Slice A, the workflow.** D1, D2, D5, the preflight, the build/deploy split,
  the rename. Gets criterion one.
- **Slice B, the app.** D4 first (small), D3 second (not small). Gets criterion
  two.

If Scott wants the round bounded to the issue as filed, Slice A ships alone,
criterion two is explicitly deferred with the reason, and issue #4 closes
partial with a follow-up filed. What must not happen is the round closing with
a green run and a still-503 healthz while the comment claims success.

For D4 specifically I would rather not add a lab-host dependency. Supplying
`SESSION_SECRET` through a slot env file means lab-admin owns a value this
project needs on every deploy. The alternative is that the app generates a
secret on first boot and persists it to `/keys/session_secret` at 0600,
keeping an explicit `SESSION_SECRET` env override for anyone who wants to
manage it externally. `/keys` is already a declared volume
(`Dockerfile:29-31`), so the secret survives restarts and redeploys and admin
sessions do not silently invalidate on every deploy. That removes the lab
dependency entirely and keeps the fail-closed posture, since a `/keys` that is
not writable still raises. I flag it as a design call rather than deciding it
alone: it changes where a secret lives, and the constitution wants that
escalated rather than assumed.

## 2. Risks

**My step 4 may not be allowed, and it is the load-bearing one.** "Read-only
recon" plausibly excludes running `docker pull` on docker.int even though it
changes no service state. If it is excluded, the pull-auth question survives
into the merge and step 2 becomes inference rather than proof. I would rather
have the answer than the clean boundary, but it is Scott's boundary to set.

**The build/deploy split is more change than the issue asked for, on the one
file the round must not get wrong.** Every line I add is a line that can be
wrong on `main` where I cannot test it, which is the exact failure mode I am
arguing against. The specific hazard is `needs.build.outputs.digest`: job
outputs from `docker/build-push-action` marshal through `$GITHUB_OUTPUT` and I
have not verified the digest survives the job boundary intact rather than
arriving empty. If it arrives empty, the deploy ssh's a bare
`ghcr.io/sentania-labs/vcf-mcp@` and fails on `main`. Step 1 does not catch
this, because on a round branch the `deploy` job is skipped and the output is
never consumed. Honest mitigation: a throwaway `echo` step in the round-branch
`build` job that prints the digest, which proves the value exists but not that
it crosses the boundary. The conservative alternative is to leave `deploy` as
one job and only gate `push:` on the ref, which tests less but adds no
untestable surface. If the critique round pushes back here I think the pushback
is well founded.

**I may be wrong about the permissions scope argument.** My claim that a
workflow-level block *reduces* the `test` job's token is worth checking against
the repo's actual default workflow permissions setting, which I did not read
(it is under org or repo Actions settings, not in any file). If the default is
already `contents: read`, then workflow-level `packages: write` does widen
`test`, and codex-worker's CI-security read should overrule mine.

**D5 could invalidate the whole deploy step, not just a line of it.** If the
forced command is hearthgate-shaped, the fix is not three lines and not thirty;
it is writing the compose file this repo does not have, deciding where volumes
live on the slot, and rewriting the deploy step around `docker compose`. That
is a round of its own. I would rather discover it in step 0 than in step 5.

**My D3 finding could be read as scope creep by a reviewer who wants the round
small.** It is not creep, it is the acceptance criteria, but I hold that
loosely enough to accept "defer criterion two, say so on the issue" as an
outcome. What I will argue against is closing the issue as done without saying
it.

**Step 3 assumes the image is runnable locally at all.** The Dockerfile builds
wheels for a hardcoded dependency list at line 13 rather than resolving from
`pyproject.toml`, so the installed set may not match what the tests run
against. If the container fails to start for a reason unrelated to D4, step 3
gets longer and the app slice grows.

**If I had one hour and one question**, I would spend it on D5: ask lab-admin
what the forced command behind `DOCKER_DEPLOY_KEY` accepts, verbatim. It is the
one unknown that can turn this round from a three-line fix into a rewrite, it
cannot be answered from GitHub, and every other open item has a cheaper path to
an answer. D3 and D4 I already have the answers to; they only need a decision.

## 3. Division-of-labor claim

**Slice B, the application side.** D3 and D4, the healthz contract, the
Dockerfile, and step 3's local-run proof. I built the healthz reasoning in
round 3, I found both defects here from the source rather than from the issue,
and the `/keys` persistence proposal for `SESSION_SECRET` is a call about the
app's startup posture, which is my ground.

**I am not the right owner for the workflow file.** agy-worker authored that
deploy job and owns the slot model, so D2 and D5 land better there, and
codex-worker prescribed the round-3 deploy-key design and should own the
permissions-scope call, including overruling my workflow-level argument if the
repo's default token settings say I am wrong. Splitting a three-line YAML diff
across three doers would be theater. One owner for the file, one reviewer,
done.

That gives two slices in two disjoint file sets (`.github/workflows/` and
`src/` plus `Dockerfile`), which merge into the round branch without conflict.
I am happy to be the non-author reviewer on Slice A.

If the round is scoped to Slice A only, then the right answer is one doer and
it is not me, and I would say so without complaint.

## 4. Rough estimate

- Slice A, workflow: half a day of work, most of it waiting on runs.
- Slice B, D4 alone: a couple of hours, including the `/keys` persistence and
  its tests.
- Slice B, D3: one to two days. A concrete `AuditRepository` against durable
  storage, its startup reconciliation pass (`contracts.py:259-261` requires
  closing every non-terminal attempt as `outcome_unknown`), factory wiring, and
  tests against real storage rather than the field-backed mock codex-worker
  already rejected once.
- Verification steps 0 through 6: a day, dominated by the lab-admin round trip
  in step 0.

**What blows it up:**

1. **D5 lands badly.** Forced command is not what the workflow assumes. Add a
   round: compose file, slot volume layout, deploy step rewritten to the
   hearthgate shape.
2. **Package pull auth needs an org change.** Not a team decision, so it
   becomes a wait on Scott plus whatever the org's package policy turns out to
   allow.
3. **D3's storage choice becomes an architecture argument.** SQLite versus
   append-only file versus something else is a dependency decision, and a new
   dependency escalates to the principal rather than being decided in a slice.
   If that argument opens, Slice B stops being a day and starts being a round.
4. **Nobody can run step 3 or step 4** because the boundary excludes them. Then
   the estimate does not grow, but the confidence does not either, and the
   merge to `main` goes in carrying risks we chose not to buy down.
