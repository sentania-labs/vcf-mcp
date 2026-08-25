# Round 4 phase 2 critique, claude-worker

Critiquing `codex-worker` (`codex/r4-deploy-permissions` at `c1558944b00c`)
and `agy-worker` (`agy/r4-deploy-permissions` at `996deaac2c4b`).

All recon below is read-only. No `POST/PATCH/PUT/DELETE`, no ssh, no state
change to org, repo, package, or lab host. The two registry token calls are
unauthenticated `GET`s against ghcr.io's token endpoint, which mint a read
scope and change nothing.

## 0. What I verified before writing a word

Four checks the round asked for, and two I added.

**Repo default workflow permissions.** `gh api
repos/sentania-labs/vcf-mcp/actions/permissions/workflow` returns
`{"default_workflow_permissions":"read","can_approve_pull_request_reviews":true}`.
This settles question 1 against me. See section 3.1.

**The secrets.** Confirmed independently. Repo secrets: `DOCKER_DEPLOY_KEY`,
and nothing else. Repo variables: none, `total_count: 0`. Org secrets visible
to this repo: `AWS_*`, `DNS_SERVER`, `DOCKER_HUB_*`, `KRB*`,
`REPO_ACCESS_TOKEN`, `SERVICEACCOUNT*`, `VCFA_REFRESH_TOKEN`,
`VCF_LAB_ALL_APPS_REFRESH_KEY`. Org variables: `VCFA_URL`. So
`DOCKER_INT_DEPLOY_KEY`, `DEPLOY_HOST`, and `SERVICE_URL` do not exist at
either level. Both peers who claimed this are right.

**`/healthz` cannot return 200.** Confirmed from source. `Dockerfile:38` runs
`uvicorn vcf_mcp.app:create_app --factory`, uvicorn calls the factory with
no arguments, `audit_repository` defaults to `None` (`app.py:54`),
`app.state.audit_repository` is set to `None` (`app.py:74`), and `healthz`
takes the `else` branch and returns 503 unconditionally (`app.py:27-34`).
`grep -rn AuditRepository src/` returns only `contracts.py:256` (a `Protocol`),
`app.py`, and `dispatcher/core.py`. `grep -rln 'sqlite\|aiosqlite' src/ tests/
pyproject.toml` returns nothing. There is no concrete implementation to inject.
Separately `app.py:57-59` raises `RuntimeError` without `SESSION_SECRET`, and
`find . -name 'compose*.y*ml' -o -name 'docker-compose*'` is empty, so nothing
supplies it. Live endpoint is 503 today.

**Two checks I added, and they are the most consequential findings in this
critique.**

First, the sibling's shape. `sentania-labs/hearthgate` does not have one
workflow. It has `build.yml` (trigger `push: [main, "round/*"]` plus
`pull_request`, one job, `push: ${{ github.event_name != 'pull_request' }}`)
and a separate `deploy.yml` (trigger `workflow_run` on Build completing).
`build.yml` carries `permissions: {contents: read, packages: write}` at
workflow level. `deploy.yml` carries `permissions: {contents: read, packages:
read}`. hearthgate's repo config is `vars.DOCKER_DEPLOY_HOST` (a repository
*variable*) and `secrets.DOCKER_DEPLOY_KEY` (a secret). There is no
`SERVICE_URL` and no health gate anywhere in it.

Second, and this one settles the round's loudest argument:
**hearthgate's GHCR package is private, and its deploy pulls it anyway.**

```
curl -s "https://ghcr.io/token?scope=repository:sentania-labs/hearthgate:pull&service=ghcr.io"
  -> {"errors":[{"code":"UNAUTHORIZED","message":"authentication required"}]}

# control, a known-public package on the same endpoint
curl -s "https://ghcr.io/token?scope=repository:home-assistant/home-assistant:pull&service=ghcr.io"
  -> {"token":"djE6aG9tZS1hc3Npc3RhbnQv..."}
```

A public GHCR package mints an anonymous pull token. hearthgate's does not, so
hearthgate's package is private. And hearthgate's `deploy.yml` runs
`ssh ... "docker compose --project-directory /srv/services/hearthgate pull"`
with **no registry login step anywhere in the workflow**. A private package
pulled successfully with no credential supplied by the workflow means the
credential lives on the docker.int host, at the daemon level.

That is the answer to the question both peers named as their biggest unknown,
and it is the opposite of the answer agy-worker assumed.

---

## 1. codex-worker

### 1.1 Steelman

The strongest version: *the permission block is the only part of this repair
anyone has evidence for, so scope the token change to the one job that needs
it, change nothing else in a file that has never successfully run, and convert
every other defect into a named pre-merge gate rather than a speculative edit.
Because the one test available runs on `main` and cannot be re-run cleanly,
attribution of the next failure is the scarce resource, and every unrelated
line in the diff spends it.*

The premise it left implicit, which makes it stronger: an unattributable
failure on `main` costs more than a delayed merge, because the next failure is
diagnosed against a workflow that differs from the last one in several places
at once, and nobody can say which change moved the needle. Under that premise
codex's minimalism is not timidity, it is protecting the signal.

Two places codex beats my proposal outright, and I say so plainly:

- **Job-level `permissions:`.** Codex is right and I was wrong. See 3.1.
- **The package visibility posture.** Codex wrote "Making the package public
  manually would be a state-changing workaround and is outside this round. The
  slot should instead have an established authenticated pull contract." Codex
  reasoned to the correct answer without the evidence, and my hearthgate token
  probe now proves it: the sibling's package is private and the host is already
  authenticated. Codex called this correctly against agy, who proposed the
  workaround as the plan.

Codex's step 1 (scan the diff for an em-dash or a secret value before merge) is
also the only mechanical constitution check any of the three of us proposed. I
did not propose it and I should have.

### 1.2 Attack

**A1. Codex's step 3 is a blocking pre-merge gate that cannot pass, ever, at
any digest.** Codex requires: "Build the candidate image locally, start it with
synthetic runtime configuration and temporary writable volumes, and require its
local `/healthz` to return 200." That 200 is unreachable. The container entry
point is `create_app --factory` with no arguments, so `audit_repository` is
`None` and `healthz` returns 503 on the `else` branch. Injecting a repository
is not a matter of configuration, because there is no concrete
`AuditRepository` anywhere in `src/`. No volume mount, no environment variable,
and no "synthetic runtime configuration" changes this.

So codex's runbook has exactly two outcomes: the round blocks forever on a gate
that no workflow change can satisfy, or someone quietly downgrades the gate
mid-round and the merge proceeds with the gate's protection gone and its
authority still claimed. This is worse than not having the gate, because a gate
that gets waived once teaches the next round that gates get waived.

This is not a nitpick about a runbook line. Codex's step 3 is the only place
its proposal touches the application at all, and it treats `/healthz` as a
black box that either works or does not. Codex never read `app.py`. Had it, the
same step would have produced the round's most important finding instead of its
most impossible gate.

**A2. Codex never concludes that acceptance criterion two is out of reach, and
that is the single biggest omission in its proposal.** Codex gets within one
sentence of it. Its step 3 says "a build failure, crash, or local 503 is an
application or image failure, not a deployment-permission failure." That
diagnosis is exactly right. But codex then routes the finding into a gate and
never says the consequence out loud: if `/healthz` returning 200 is an
application defect and this round is scoped to a workflow file, then criterion
two is not achievable by this round's deliverable and the issue is mis-scoped as
filed. Codex proposes no scope split, no explicit deferral, and no follow-up
issue. Its proposal, followed exactly, ends with a green Actions run, a 503 at
`vcf-mcp.int.sentania.net/healthz`, and a runbook whose step 7 fails with no
guidance on what to do about it beyond "fails acceptance."

What should happen instead: replace step 3 with two things. A local run whose
*expected* result is documented as a 503 with body `{"ready": false, "error":
"Audit repository is unavailable"}`, which proves the image builds, starts, and
binds, and which is a genuinely useful pre-merge gate that can actually pass.
And a stated recommendation on the issue that criterion two is deferred to a
second slice with a named reason.

**A3. Codex's step 3 would also fail before it reached `/healthz`, for a
different reason it did not find.** "Synthetic runtime configuration" is doing
load-bearing work. `app.py:57-59` raises `RuntimeError` when `SESSION_SECRET`
is unset, so the factory raises and uvicorn exits nonzero. Locally, a reviewer
supplies `-e SESSION_SECRET=...` without thinking about it and the container
starts. On the slot, nothing supplies it: there is no compose file in this repo
(despite `docs/SPEC.md:66` promising "one container image (plus compose file)"),
the deploy step passes only an image reference, and the workflow sets no
container environment.

So codex's local gate is not merely unsatisfiable, it is unsatisfiable in a way
that *inverts*: the one difference between local and slot that matters is the
one thing the local harness papers over. A gate whose passing condition is
supplied by the harness and absent in production is worse than no gate, because
it converts a production defect into a false green.

**A4. Codex's diff and codex's caveat contradict each other on the rename.**
The diff does `- secrets.DOCKER_INT_DEPLOY_KEY` / `+ secrets.DOCKER_DEPLOY_KEY`
today. The prose says the rename "must be confirmed against the slot onboarding
record before implementation" and that if `DOCKER_DEPLOY_KEY` is not the
`vcf-mcp` forced-command key, the fix is to provision a correctly named
secret. Both cannot be the recommendation. As written, a reviewer takes the
diff, the confirmation step gets folded into the general pre-merge gate, and
the assumption ships.

I concede the underlying point: codex flagged the "is `DOCKER_DEPLOY_KEY`
actually this slot's key" assumption more sharply than I did, and my proposal
performed the same rename with less hedging. The correction applies to my diff
too. But the resolution is not to hedge in prose and act in YAML. It is to make
the assumption fail loudly at runtime, which is what a preflight step does and
what codex has not proposed.

**A5. Codex asks Scott to provision `DEPLOY_HOST` and `SERVICE_URL` without
specifying their format, and the sibling shows the format is not obvious.**
hearthgate stores its target as `vars.DOCKER_DEPLOY_HOST`, a repository
*variable*, not a secret, and its ssh line is `ssh ... -i deploy_key ${{
vars.DOCKER_DEPLOY_HOST }} "docker compose ..."` with **no user prefix**, which
means the variable's value carries the whole `user@host` target (or the ssh
config supplies the user). This repo's workflow hardcodes `deploy@$DEPLOY_HOST`.

So "provision `DEPLOY_HOST`" is ambiguous in a way that produces
`deploy@deploy@docker.int...` if Scott follows the sibling's convention, and a
bare hostname that works only if `deploy` really is the right user if he does
not. Codex's step 2 says "read repository metadata and verify the selected
deploy-key secret, `DEPLOY_HOST`, and `SERVICE_URL` exist." Existence is not the
check that fails here. A secret with the wrong shape exists and is wrong.

Also, a lab hostname is not a credential. hearthgate models it as a variable,
which is readable in logs and in the API, which is exactly what you want for a
value you have to eyeball when the deploy breaks. Codex accepts the workflow's
`secrets.` framing without examining it, then complains in its own risk section
about the deploy shell's poor diagnostics. Making the host a secret is one of
the causes of that.

**A6. Codex's answer to a process gate that already failed is another process
gate.** `TEAM-STATE.md:321` records that "the lab FQDNs are out of the workflow
and into `DEPLOY_HOST` / `SERVICE_URL` Actions secrets." The FQDNs came out.
The secrets were never created. A round-3 sign-off reviewed that diff and
closed the item, because a diff is all a diff can show. Codex's remedy for the
resulting breakage is step 2, a human reading repository metadata before merge:
structurally the same kind of check that just failed, run by the same kind of
reviewer.

The machine-enforced version costs eight lines: a preflight step at the top of
the deploy job that tests each required value for emptiness and exits 1 naming
the missing ones. It cannot be forgotten, it survives into every future round,
and it converts three silent empty-string expansions into one legible error
line. Codex's own risk section says "GitHub resolves an absent secret to an
empty value, which would make the first newly reachable deploy step fail" and
then does nothing structural about it.

**A7. Codex's step 5 requires an observation the workflow cannot make.**
"Require the slot deploy step to pull that digest, not merely accept an SSH
command." The deploy step runs `ssh ... vcf-mcp
ghcr.io/sentania-labs/vcf-mcp@${IMAGE_DIGEST}` and captures nothing. There
is no output parsing, no post-deploy `get-digest` readback compared against the
pushed digest, and `/healthz` returns no version or digest field to compare
against (see `app.py:19-26`, the body is `ready`, `audit_writable`,
`unreconciled_outcome_unknown_count`). As written the criterion cannot be
evaluated from the run log, so in practice it gets marked satisfied by the ssh
exiting zero, which is the exact thing codex said was insufficient.

If codex wants this check, it has to ask for the thing that makes it possible:
a second `get-digest` readback after deploy, compared to `steps.build.outputs.digest`,
which is three lines and is a real improvement. Naming the requirement without
the mechanism produces a checklist item that is always ticked and never tested.

**A8. Codex declines the round-branch test loop and pays for it in every other
section.** Codex's proposal contains the phrases "the one main-only test",
"another blind main merge", and "changing all of them in the permission repair
would make the one main-only test harder to attribute." Every one of those
costs is downstream of accepting that the build can only be tested on `main`.
It cannot: the workflow already triggers on `push: branches: [main, "round/*"]`,
and hearthgate's `build.yml` runs on `round/*` and pushes on every non-PR event,
which means the sibling this repo is copying **already builds and pushes from
round branches**. The scarcity codex is optimizing around is self-imposed. See
3.4.

---

## 2. agy-worker

### 2.1 Steelman

The strongest version: *the permissions block is not in dispute and neither is
the diagnosis, so apply the minimal correct fix, add the one line that prevents
a foreseeable and annoying second failure (repository linkage on a first-ever
package create), and put the analytical effort into predicting where the run
will actually die rather than into the diff. The prediction is the deliverable,
not the YAML.*

The implicit premise that makes it stronger: a first-ever deploy through a
never-executed path will fail somewhere regardless of how carefully the diff is
reviewed, so the highest-value artifact is a ranked list of where it will fail
and what each failure looks like in the log, so the person watching the run
recognizes the failure instead of debugging it from scratch.

Two things agy got right that I want on the record:

- **The rename recon.** agy independently reached the same conclusion I did,
  and I confirm it again here: `gh api .../branches/main/protection` returns
  `404 Branch not protected`, and `consensus.yml` references no other workflow
  and no check-run name. agy and I agree the rename is free. Codex is the
  outlier.
- **agy is the only one of the three who named the digest-versus-tag parsing
  question at the remote end**, even though it then scored it wrong. The
  question is real and nobody else raised it.

### 2.2 Attack

**B1. agy did not find the missing secrets, and its entire verification runbook
is built on a step that cannot execute.** agy's diff leaves
`DEPLOY_KEY: ${{ secrets.DOCKER_INT_DEPLOY_KEY }}` untouched. That secret does
not exist. Trace what agy's Step 2 ("the pipeline moves to the `Deploy to slot
and verify health` step, executing `ssh ... ghcr.io/...@<DIGEST>`") actually
does:

1. `echo "$DEPLOY_KEY" > "$KEY_PATH"` writes a single newline. `$KEY_PATH` is a
   zero-content key file.
2. `PREV_DIGEST=$(ssh -i "$KEY_PATH" ... deploy@$DEPLOY_HOST vcf-mcp
   get-digest || echo "none")`. `$DEPLOY_HOST` is empty, so the ssh target is
   the literal string `deploy@`. This fails, and `|| echo "none"` swallows it.
   The one diagnostic signal available is discarded by design.
3. The second `ssh` on line 91 has no `|| ` guard. `run:` blocks execute under
   `bash -e`. The step exits nonzero here.

The job dies at line 86-91 with an ssh error against a host named `deploy@`,
using an empty key. agy's Step 3, "The Catch" (the private-package pull
failure), is never reached, because the pull never happens. agy has predicted
the wrong failure at the wrong step for the wrong reason, and its stated
remediation for that failure is a state change to a package.

This matters more than a missed detail. agy claims the slot-model ownership
("Because I authored the deploy job...I am best positioned to interpret the
deploy step's failure modes"). The two residents who did not author it both
found that three of its four inputs do not exist. Ownership of a component is
being offered here as a reason to trust a prediction about it, and the
prediction is wrong in the component's own configuration.

**B2. agy's primary risk is empirically false, and its remediation is a public
disclosure nobody asked for.** agy: "If the multi-tenant `$DEPLOY_HOST` pulls
anonymously, the deploy step will immediately fail with an authentication
error...a human (Scott) must manually change the package visibility to Public
in GHCR settings and re-run the failed job."

The sibling refutes this. hearthgate's package is private (anonymous token
request returns `UNAUTHORIZED`, while a known-public control on the same
endpoint mints a token), and hearthgate's `deploy.yml` pulls it with
`ssh ... "docker compose ... pull"` and **no registry login step in the
workflow at all**. A private package pulling successfully with no
workflow-supplied credential means the docker.int host holds a GHCR credential
at the daemon level. Private is the working convention on this host, not the
break point.

So agy's "primary break point" is very likely not a break point, and its
proposed fix would make an unofficial VCF Ops project's container image
world-readable to fix a problem the lab has already solved a different way.
This repo's constitution opens by establishing that this is an unofficial
personal-lab project that must not imply an official offering. Publishing its
image to the world is not a button click, it is a disclosure decision, and agy
files it under "adding however long it takes the admin to click the button."

The correct remediation, which codex reached by reasoning and I have now
confirmed by measurement, is to verify the host's existing GHCR credential
covers the new package. If the credential is an org-scoped PAT it already does
and there is nothing to do. That is a read-only question for lab-admin, not a
visibility flip.

**B3. agy's justification for the `org.opencontainers.image.source` label is
wrong, and it is wired to B2 in a way that will mislead a reviewer.** agy: "A
first-time GHCR push via `GITHUB_TOKEN` creates the package unlinked in the org
namespace. Explicitly linking it ensures it is tied to this repository, which is
required for repository-level access control and visibility inheritance."

Two errors. The unlinked-by-default behavior is the *PAT* push case; a push
authenticated with `GITHUB_TOKEN` from the owning repository is linked by GHCR
on that basis. And a label does not affect visibility under any push path.
Labels are metadata; visibility is package settings.

I am not arguing against the label. It is cheap, hearthgate gets the equivalent
for free via `docker/metadata-action`, and it is the right belt-and-braces move
for the day someone switches to a PAT. Keep it. What has to be struck is the
justification, because agy's own primary risk is a visibility problem, and a
reviewer reading these two claims together will conclude the label mitigates
it. It does not. The proposal therefore reads as containing a fix for its own
headline risk when it contains no such thing.

**B4. agy predicts a green health check for an endpoint that returns 503 by
construction.** agy's Step 4: "the workflow loops waiting for `/healthz` to
return 200. We observe the workflow log to confirm the health check succeeds
and exits 0." It will not. `create_app` is invoked by uvicorn with no
arguments, `audit_repository` is `None`, and `healthz` returns 503
unconditionally. There is no concrete `AuditRepository` in `src/` to inject.
And before that, `app.py:57-59` raises on the missing `SESSION_SECRET` that
nothing in the deploy path supplies, so the container exits and there is no
listener at all.

agy's only stated healthz risk is a cold-start timeout: "If the app takes
longer to boot on a cold start, the pipeline will roll back and fail, even if
the deployment was fundamentally sound." That framing treats a permanent,
structural 503 as a transient timing problem, which is the most expensive
possible misdiagnosis to hand to whoever watches the run. They will extend the
timeout and try again.

Following agy's proposal to its end: the run goes red, `PREV_DIGEST` is `none`
on a first-ever deploy, the workflow logs "No prior digest found to roll back
to" and exits 1, and criterion two is as far away as it was before the merge.
agy's estimate for this is "less than 10 minutes."

**B5. agy's hour-question is aimed at the question the sibling already answers,
and away from the one nothing answers.** agy would spend its hour on the
host's GHCR credential. Section 0 answers that from public data in about a
minute, for free, without asking anyone.

The question nothing in this repo answers is whether `vcf-mcp get-digest`
is a command the slot can run. `grep -rn 'get-digest' docs/ .team/` finds that
string nowhere outside this repo's own workflow. The only description of the
interface is `docs/proposals/2/SPEC.md:488`, "the onboarded slot's
forced-command key", which names no verbs. And the sibling, onboarded to the
same host with a same-named `DOCKER_DEPLOY_KEY` secret, uses that key to `scp` a
compose file and run three arbitrary `docker compose` commands. That is a
general-purpose shell key, not a forced command with a per-project subcommand
grammar.

If docker.int onboarded this project the way it onboarded hearthgate, then
`vcf-mcp get-digest` and `vcf-mcp <image-ref>` are not things the key
can run, and both ssh invocations in the deploy step are written against an
interface that does not exist. That is not a line to fix, it is the whole step.
agy's actual digest risk ("standard Docker/Containerd tools natively accept
`image@sha256:...`, making this risk low") assumes the wrapper exists and worries
about its argument parsing. The wrapper is the risk. The argument format is
downstream of a premise nobody has checked.

I flagged this as my D5 and my own hour-question, so I am not claiming
neutrality. But agy is the resident claiming to own the slot model, and this is
the slot model's one unattested assumption.

**B6. agy's estimate is built on an action the constitution forbids it to
take.** "Less than 10 minutes to write the commit and merge the PR."

I will state this in the terms the round asked for: **as written, this
violates CLAUDE.md, "Workspace conventions": "No self-merge and no
self-approval. The resident that wrote a change never merges it and never signs
off on it as its own reviewer. Merge authority belongs to the orchestrator."**
It also skips the blocking gate in the same section, "Before a doer's slice
integrates, another resident (not the author) must review the diff in-worktree
and write a pre-integration sign-off marker under `.team/signoffs/`. No marker,
no integration." And under the round-branch model doers do not open PRs at all.

I accept that this is most likely loose phrasing rather than an intent to
self-merge. But the estimate is the section it appears in, and the estimate is
"10 minutes" precisely because it counts only the typing and omits peer review,
sign-off, integration, and the external review round. An estimate that omits
the gates is not conservative by accident; it is the number that gets quoted
back when the round runs long.

**B7. agy is the only proposal with no verification step before the merge.**
Every one of agy's four steps begins after the merge to `main` has happened.
There is no local image build, no metadata read, no preflight, and no
round-branch run. Its entire plan is "merge and observe", with a human
recovering interactively from whatever happens. Given B1 and B4, what will be
observed is a red run failing at an ssh to `deploy@` for reasons unrelated to
any risk agy listed.

---

## 3. The six questions

### 3.1 Where `permissions:` goes: job level. I was wrong.

`default_workflow_permissions` on this repo is `read`. My proposal argued
workflow-level placement is a net token *reduction* for the `test` job, and
explicitly conditioned that argument on a setting I had not read. I have now
read it and the argument is dead. The `test` job's token today is already
read-only. A workflow-level `permissions: {contents: read, packages: write}`
block would take `test` from "cannot write anything" to "can create and
overwrite organization container packages", which is a real widening in the one
scope that matters, granted to the job that runs `pip install -e .[test]` and
executes the test suite. That is the job with the largest untrusted-input
surface in the workflow.

Codex and agy are both right, and codex's reasoning ("giving the test job
package creation rights increases the authority of dependency installation and
test execution for no benefit") is the correct one.

I also have to withdraw the evidence I offered, not just the conclusion. I
wrote that hearthgate "pushes to `ghcr.io/sentania-labs/hearthgate` from the
same org with exactly `permissions: {contents: read, packages: write}` at
workflow level." True, and misleading in the way that matters: hearthgate's
`build.yml` contains **one job**, which is the job that needs the scope. Its
workflow level and its job level are the same set. hearthgate's *other*
workflow, `deploy.yml`, drops to `packages: read`. So the sibling's actual
practice is scope-per-workload, and it is evidence *for* codex's placement, not
mine. I cited it for the opposite conclusion, and a reviewer who trusted my
citation without opening the file would have been led wrong. That is worse than
being wrong and I want it recorded as such.

**Settled: job-level on `deploy`, exactly as codex's diff has it.** Nothing is
needed on `test`, because with the repo default at `read` it is already
minimal. Note for whoever writes it: job-level placement sets every unlisted
scope to `none`, and the `deploy` job runs `actions/checkout@v4`, so
`contents: read` must stay in the block. Codex's diff has it.

### 3.2 The missing secrets: rename **and** preflight, and fix the shape too.

Confirmed independently in section 0. On what follows, the rename alone is not
enough and the preflight alone is not enough.

**Rename is necessary but rests on an unconfirmed premise.** Nobody has
confirmed `DOCKER_DEPLOY_KEY` is this slot's key. What we now know is that it
was created for this repo, and that hearthgate uses an identically-named repo
secret for the same host, which makes it the naming convention rather than a
coincidence. That raises my confidence and does not make it a fact. Codex is
right to flag it; codex is wrong to flag it in prose while performing it in the
diff.

**Preflight is what turns the unconfirmed premise into a legible failure.** An
eight-line step at the top of the deploy job that checks each required value
for emptiness and exits 1 naming the missing ones. This is the part codex does
not have and needs. Its absence is exactly why `TEAM-STATE.md:321` could record
work that did not happen and survive a sign-off: nothing executable ever
asserted the secrets existed.

**And the third thing neither peer raised: `DEPLOY_HOST` and `SERVICE_URL`
should be variables, not secrets, and their shape has to be specified.**
hearthgate uses `vars.DOCKER_DEPLOY_HOST` and embeds the user in the value. This
workflow hardcodes `deploy@$DEPLOY_HOST`. Whoever creates the config needs to be
told which convention to follow or the value will be wrong in a way the
preflight cannot catch, since a wrong-shaped non-empty value passes an emptiness
check. A lab hostname and a lab service URL are not credentials, they are
identifiers already visible in `TEAM-STATE.md`, and making them variables buys
back the log legibility that codex separately complains is missing from the
deploy step.

Recommendation for the workplan: name them `DOCKER_DEPLOY_HOST` (variable, value
matching hearthgate's convention) and `SERVICE_URL` (variable), keep
`DOCKER_DEPLOY_KEY` as the only secret, and have the preflight check all three.

### 3.3 Whether `/healthz` can return 200: it cannot. Split the round.

Confirmed from source in section 0, on all three legs: the factory takes no
arguments from uvicorn, there is no concrete `AuditRepository` to inject, and
the container raises on a `SESSION_SECRET` nothing supplies. Neither peer's
proposal is affected in its diff, and both are affected in their runbook, and
neither drew the conclusion.

**What the round should do: split into two slices and say so on the issue.**
Not defer criterion two silently, and not fold the application work into this
round's workflow slice.

- **Slice A, the workflow.** Permissions, secret names and shapes, preflight,
  the build/deploy split, the rename. Gets criterion one.
- **Slice B, the application.** `SESSION_SECRET` (small), then a concrete
  `AuditRepository` (not small, and it carries a storage-backend choice that
  escalates to Scott as a dependency decision). Gets criterion two.

Against "just defer criterion two": deferral without a filed slice means the
issue closes partial and the finding decays into a `TEAM-STATE.md` line, which
is precisely how the missing-secrets item got lost between round 3 and now. It
is also not a new finding. codex-worker denied this same item in round 3
(`.team/signoffs/agy-r3-delivery-19efb0cdab60.md`, claim 4, "wire the concrete
durable repository in the application factory"), it was recorded PARTIALLY
CLOSED, and it has now caused a second round to be filed with an unreachable
acceptance criterion. Twice-carried findings need a slice, not a third carry.

Against folding Slice B into this round: Slice B is a day or two, it touches
`src/`, and its storage choice is an escalation. Slice A is blocked on none of
that and should not wait.

The two slices touch disjoint file sets (`.github/workflows/` versus `src/` and
`Dockerfile`), so they integrate into the round branch without conflict.

### 3.4 The build/deploy split: yes, and the sibling already does it.

Codex's objection is that the split spends untestable YAML on the one file the
round must not get wrong. That objection is coherent only under the premise
that the build can only be exercised on `main`. The premise is false, and the
strongest evidence is the workflow this repo is copying: hearthgate's
`build.yml` triggers on `push: branches: ["main", "round/*"]` and pushes on
`${{ github.event_name != 'pull_request' }}`, which means **every round branch
in hearthgate builds and pushes to GHCR**. The pattern codex is protecting
`main` from is the sibling's normal operation.

This repo's own workflow already triggers on `round/*` too (line 5). The only
reason nothing runs there is the `deploy` job's `if: github.ref ==
'refs/heads/main'`. Splitting build out from that gate lets the push half run on
the round branch under identical conditions (same runner, same `GITHUB_TOKEN`,
same permissions block, same registry, same image name), which proves the
permissions fix, creates the package, and exposes its visibility and linkage,
all before the merge.

**Where codex's objection lands, and where I now concede.** I flagged
`needs.build.outputs.digest` as an unverified job boundary, and I still have not
verified it. Notably, hearthgate did not use a cross-job output either: its
`build.yml` writes the digest to `image-digest.txt` with a comment about
`release`/`deploy` reusing it, and its `deploy.yml` in fact ignores digests
entirely and pulls the `:main` tag via compose. So the sibling's evidence
supports the split and does *not* support my mechanism.

The fix removes the boundary rather than testing it: **deploy the immutable
`:${{ github.sha }}` tag the build already pushes, instead of passing a digest
across jobs.** The tag is per-commit and already in the workflow at line 67, and
`github.sha` is available in both jobs with no plumbing. This deletes the one
piece of untestable YAML codex objected to, and it deletes it from my proposal,
not from codex's.

**What I will not adopt from hearthgate:** its two-file `workflow_run` shape.
`workflow_run`-triggered workflows execute the copy of the file on the default
branch, so a `deploy.yml` under `workflow_run` can never be tested from a round
branch at all. That is strictly worse for this round's problem than two jobs in
one file. Nobody should read "copy hearthgate" as "copy `workflow_run`."

**One cost I owe the split, which codex did not name and should have.** Pushing
from round branches means the package accumulates images built from unreviewed
code. In a private package on a private host, tagged per-commit, with `main`
deploying a specific ref, I accept that. But it deserves a line in the workplan
rather than being smuggled in as a testability win, and it is a fair thing for
Scott to veto.

### 3.5 The rename: do it now, in its own commit. Codex is outvoted on evidence.

agy and I independently reached the same recon result and I have confirmed it a
third time here: no branch protection (`404 Branch not protected`), so no
required status checks exist to break, and `consensus.yml` references no other
workflow and no check-run name. Every remaining mention of `ai-log-depot` is
prose in `TEAM-STATE.md`, `docs/`, and `.team/`. Nothing machine-readable
consumes either the file name or the check-run name.

Codex's counter is a good general principle: do not add an unrelated variable
while diagnosing a path that has never run. It fails on the particulars here for
two reasons. First, a variable is only a variable if it can affect the outcome,
and we have positively established that this one cannot; treating a
zero-coupling rename as a confound is cargo-culting the principle past its
premise. Second, codex's principle is priced in "one main-only test" currency,
and 3.4 shows that currency is not scarce. With the split, the diagnosing run is
a round-branch run that can be repeated.

The affirmative case: leaving `ai-log-depot` in place means every future
resident reading this repo's CI has to learn that the workflow is named after a
different project, and the round after this one will file the same rename with
the same "not now, we are diagnosing" objection, indefinitely. There is also a
real closing window: `main` is unprotected today, so no ruleset pins a check
name. The first time someone adds required status checks, the rename acquires a
cost it does not have now.

Do it as a standalone `git mv` plus one-line `name:` commit, ordered *before*
the substantive commit, so the substantive diff is readable as a diff rather
than as a whole-file delete and add pair. That is the part that answers codex's
attribution worry: the two changes are separable in the history, and if the
round-branch run misbehaves, `git show` on the substantive commit is three
lines.

One cost I will state since neither peer did: the Actions sidebar treats a
renamed file as a new workflow, so the existing run history stops grouping with
it. For a workflow whose entire history is one green test job and one failed
deploy, that is not a loss.

### 3.6 What Scott is actually being asked to approve

The round's output is a spec and a workplan Scott approves on the issue, so
anything needing his hand has to be a numbered decision, not a runbook step.

**Codex: partly good, under-specified.** It surfaces secret provisioning, the
slot-contract confirmation, and package visibility approval, and it deserves
credit for being the only proposal that explicitly refuses to treat a
visibility flip as a team-level workaround. But it leaves the format of the
values unspecified (A5), and it never surfaces the largest decision of all,
which is that criterion two is out of reach and the round's scope needs to
change (A2). A scope split is the single most consequential thing on Scott's
desk this round and codex does not put it there.

**agy: one decision surfaced, and it is the wrong one.** agy surfaces exactly
one item for Scott, the package visibility flip, which section 0's measurement
says is probably unnecessary and which as proposed is a public disclosure of an
unofficial project's image. It surfaces none of: the missing secrets, their
format, the forced-command grammar, or the scope problem. And its plan has Scott
performing the visibility change *interactively, mid-run, to unblock a red
pipeline*, which is the worst possible framing for a disclosure decision.

**Mine: better coverage, one thing buried.** I surfaced the missing secrets, the
forced-command question, package visibility, and the scope split as explicit
decisions. But I put the `SESSION_SECRET` design call (generate on first boot
and persist to `/keys/session_secret` at 0600 with an env override, rather than
depending on lab-admin to supply a value on every deploy) inside a scope
discussion in section 1.5 instead of listing it as a decision. It changes where a
secret lives, which the constitution routes to the principal. It should be a
numbered decision. That is my correction to make, not a peer's.

**The decision list I would put on the issue:**

1. Split the round into Slice A (workflow) and Slice B (application), with
   criterion two explicitly moved to Slice B and issue #4 closing partial. This
   is the one that changes what the round delivers.
2. Provision `DOCKER_DEPLOY_HOST` and `SERVICE_URL` as repository *variables*,
   with the value shape specified (whether the host carries the `deploy@`
   prefix). Values never enter the repo or transcripts.
3. Confirm with lab-admin, read-only, what the forced command behind
   `DOCKER_DEPLOY_KEY` accepts. Specifically whether `vcf-mcp get-digest`
   and `vcf-mcp <image-ref>` are real, or whether this slot is a
   hearthgate-shaped general shell key expecting a compose file. If it is the
   latter, Slice A grows a compose file and a slot volume layout and becomes a
   round of its own.
4. Approve or veto pushing images from `round/*` branches to GHCR.
5. Decide where `SESSION_SECRET` comes from: a slot-supplied env value (a
   standing lab-admin dependency on every deploy) or first-boot generation
   persisted to the already-declared `/keys` volume.

Package visibility is deliberately **not** on that list. Section 0's evidence
says the host is already authenticated for a private sibling package, so the
default action is to confirm the credential's scope covers the new package,
which is a read-only question. It only becomes Scott's decision if that
confirmation comes back negative.

---

## 4. Summary of concessions

- **Job-level `permissions:` is correct and my workflow-level argument was
  wrong.** The repo default is already `read`, so my "net reduction" claim
  inverts. Codex and agy both had this right.
- **My hearthgate citation was misleading**, not merely wrong. hearthgate's
  workflow-level block sits on a single-job workflow, and its second workflow
  drops to `packages: read`. The sibling supports codex's placement, and I
  cited it for mine.
- **Codex called package visibility correctly against agy**, by reasoning,
  before I had the measurement that confirms it.
- **Codex flagged the `DOCKER_DEPLOY_KEY` assumption more sharply than I did**,
  and that correction applies to my diff as well as its own.
- **Codex proposed the only mechanical constitution check** in the round, an
  em-dash and secret-value scan on the diff before merge. I did not, and it
  should be in the workplan.
- **agy's rename recon is sound** and matches mine, and agy is the only resident
  who raised remote-side digest parsing at all.
- **My `needs.build.outputs.digest` boundary was a real weakness** and codex's
  objection to added untestable YAML lands on it. I am dropping the mechanism,
  not the split: deploy the immutable `:${{ github.sha }}` tag instead.
- **I buried the `SESSION_SECRET` design call** in a scope section instead of
  raising it as a decision for Scott.
