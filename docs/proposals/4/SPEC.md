# Round 4 spec: repair the post-merge deploy path

Issue: sentania-labs/vcf-mcp#4. Round branch `round/4-deploy-permissions`.
Lane: full protocol, three doers. This document is the converged team position.
The per-worker proposals, critiques, and ballots it was synthesized from are in
this directory and are cited by SHA in `docs/decisions/011-deploy-path-repair.md`.

Nothing in this round was applied. `.github/workflows/ai-log-depot.yml` is
unmodified on every branch.

## 1. What the issue got right, and what it got wrong

Right: the diagnosis. Run 30184249021 shows `CI Pipeline` green and
`Build & Deploy` failing in 34s at `Build and push image` with
`denied: installation not allowed to Create organization package`. The
`Login to GitHub Container Registry` step passed, so the token authenticated
and was refused the create. That is the `packages: write` signature, and the
three-line block is the correct fix.

Wrong: "this permissions gap is the only thing between merged code and a
running service." Five defects sit between `main` today and a 200 from
`https://vcf-mcp.int.sentania.net/healthz`. Every finding below was
established by read-only recon and independently reproduced by at least two
residents, and the orchestrator re-ran the load-bearing ones itself.

### D1. Missing `permissions:`. Confirmed. This is the one the issue names.

The repository's `default_workflow_permissions` is `read`
(`gh api repos/sentania-labs/vcf-mcp/actions/permissions/workflow`), so no
job in this workflow can currently write anything, including packages.

### D2. Three of the four secrets the deploy step reads do not exist. Confirmed, and fatal on its own.

The workflow reads `secrets.DOCKER_INT_DEPLOY_KEY`, `secrets.DEPLOY_HOST`, and
`secrets.SERVICE_URL`. Repository secrets contain exactly one name,
`DOCKER_DEPLOY_KEY`. Repository variables: none. Organization secrets visible
to this repo: `AWS_*`, `DNS_SERVER`, `DOCKER_HUB_*`, `KRB*`,
`REPO_ACCESS_TOKEN`, `SERVICEACCOUNT*`, `VCFA_REFRESH_TOKEN`,
`VCF_LAB_ALL_APPS_REFRESH_KEY`. Organization variables: `VCFA_URL`. None of the
three referenced names exists at either level.

So on the first run that gets past D1, the deploy step writes a newline to the
key file, runs `ssh -i <empty key> deploy@ vcf-mcp get-digest` against a
host literally named `deploy@`, swallows that failure through `|| echo "none"`,
and dies on the next unguarded `ssh` under `bash -e`. Criterion one ("slot
deploy executed") fails on the very next attempt after D1 is fixed, and the one
diagnostic signal available is discarded by design.

This also contradicts `TEAM-STATE.md:321`, which records that "the lab FQDNs are
out of the workflow and into `DEPLOY_HOST` / `SERVICE_URL` Actions secrets." The
FQDNs did come out. The secrets were never created. A round-3 peer sign-off
reviewed that diff and closed the item, because a diff is all a diff can show.
Nothing executable ever asserted the other half, which is precisely why D6 below
is part of this spec rather than a nicety.

### D3. `/healthz` cannot return 200 from the container image, at any digest. Confirmed.

`Dockerfile:38` runs `uvicorn vcf_mcp.app:create_app --factory`. Uvicorn
calls the factory with no arguments, so `audit_repository` defaults to `None`
(`app.py:54`), `app.state.audit_repository` is `None`, and `healthz` takes the
`else` branch at `app.py:27-34` and returns 503 unconditionally.

Wiring one is not a configuration change, because there is nothing to wire.
`AuditRepository` (`contracts.py:256`) is a `Protocol`. It appears in `src/`
only in `contracts.py`, `app.py`, and `dispatcher/core.py`; there is no
concrete implementation, and no storage dependency anywhere in `src/`, `tests/`,
or `pyproject.toml`. The only implementations are test doubles.

This is not a new finding. codex-worker denied exactly this in round 3
(`.team/signoffs/agy-r3-delivery-19efb0cdab60.md`, claim 4, "wire the concrete
durable repository in the application factory"). It was recorded PARTIALLY
CLOSED and carried forward, and it has now caused a second round to be filed
with an unreachable acceptance criterion. A twice-carried finding needs a slice,
not a third carry.

### D4. The container raises at startup before it binds. Confirmed.

`app.py:57-59` raises `RuntimeError` when `SESSION_SECRET` is unset. The
fail-closed behavior is correct and was a round-3 review requirement. Nothing
supplies the value: there is no compose file in the repo (despite
`docs/SPEC.md:66` describing "one container image (plus compose file)"), the
deploy interface passes only an image reference, and the workflow sets no
container environment. The factory raises, uvicorn exits nonzero, the slot has
no listener, and fleet-caddy keeps answering 503.

D3 and D4 stack. Fixing D4 alone yields a live process that answers 503.

### D5. The slot's forced-command interface is an assumption, not a verified contract. UNRESOLVED.

The deploy step calls `vcf-mcp get-digest` and `vcf-mcp <image-ref>` as
forced-command subcommands. That verb string appears nowhere outside this
repo's own workflow. The nearest source, `docs/proposals/2/SPEC.md:488`, says
"the onboarded slot's forced-command key" and names no verbs.

The sibling contradicts the assumption. `sentania-labs/hearthgate`'s
`deploy.yml` uses an identically-named `secrets.DOCKER_DEPLOY_KEY` against the
same host to run `scp` of a compose file plus three arbitrary
`docker compose ... pull|up -d|ps` commands against `vars.DOCKER_DEPLOY_HOST`.
That is a general shell key, not a forced command with a per-project subcommand
grammar. If docker.int onboarded this project the way it onboarded hearthgate,
both ssh invocations in the deploy step are written against an interface that
does not exist, and the fix is not a line, it is the whole step.

This cannot be settled without ssh, which the round's read-only constraint
excludes. It is Decision 3 below.

### D6. What is NOT a defect, established by measurement rather than assumed

- **Org policy is not blocking package creation.** hearthgate pushes to
  `ghcr.io/sentania-labs/hearthgate` from the same org with exactly
  `permissions: {contents: read, packages: write}` and nothing else. If the org
  restricted container creation, hearthgate would fail identically.
- **A package visibility flip is very likely not needed, and should not be the
  plan.** hearthgate's package is private: an anonymous
  `https://ghcr.io/token?scope=repository:sentania-labs/hearthgate:pull` returns
  `UNAUTHORIZED`, while a known-public control on the same endpoint mints a
  token. And hearthgate's `deploy.yml` pulls that private package with no
  registry login step anywhere in the workflow, which means the docker.int host
  holds a GHCR credential at the daemon level. Private is the working
  convention on this host, not the break point. agy-worker's phase-1 plan named
  a visibility flip as the primary remediation; the measurement says otherwise,
  and publishing an unofficial VCF Ops project's image to the world is a
  disclosure decision rather than a recovery step.
- **fleet-caddy is genuinely resolved.** The endpoint returns 503 today. During
  round 3's spike it died at Client Hello with `SSL_ERROR_SYSCALL`. TLS now
  terminates and the proxy answers, so the per-slot config landed as the issue
  says. `.team/blocked/fleet-caddy-slot-config.md` should be closed out.
- **The rename is free.** `gh api .../branches/main/protection` returns
  `404 Branch not protected`, so there are no required status checks to break.
  `consensus.yml` references no other workflow and no check-run name. Every
  remaining mention of `ai-log-depot` is prose. Note the corollary: the
  consensus gate and CI are both advisory on `main` right now.

## 2. The converged change (Slice A)

Two commits in `.github/workflows/`, one file.

**Commit 1: the rename alone.** `git mv ai-log-depot.yml vcf-mcp.yml` plus
`-name: ai-log-depot` / `+name: vcf-mcp`. Ordered first so the substantive
diff in commit 2 reads as a diff rather than as a whole-file delete-and-add
pair.

**Commit 2: the substance.**

1. **`permissions:` on the package-pushing job only**, not at workflow level:

   ```yaml
   permissions:
     contents: read
     packages: write
   ```

   Settled 3-0. The repo default is already `read`, so a workflow-level block
   would take the `test` job from "cannot write anything" to "can create and
   overwrite organization container packages", granted to the job that runs
   `pip install -e .[test]` and executes the suite, which is the largest
   untrusted-input surface in the file. Job-level placement sets every unlisted
   scope to `none`, so `contents: read` must stay in the block because the job
   runs `actions/checkout@v4`.

2. **Split `deploy` into `build` and `deploy`.** `build` keeps the
   `if: github.repository == ...` fork gate but drops the `main` ref gate, so it
   runs on `round/*` too. `deploy` keeps `if: github.ref == 'refs/heads/main'`
   and `needs: build`.

   **Deploy the immutable `:${{ github.sha }}` tag the build already pushes at
   line 67. Do not pass a digest across the job boundary.** `github.sha` is a
   context expression available in both jobs with no plumbing, which deletes the
   one piece of untestable YAML the critique round objected to.

3. **A preflight step at the top of `deploy`** that tests each required input
   for emptiness and exits 1 naming the missing ones, without printing values.
   This is what turns three silent empty-string expansions into one legible
   error line, and it is the machine-enforced answer to the process gate that
   already failed once (see D2).

4. **Correct the deploy inputs**, conditional on Decision 2:
   `secrets.DOCKER_INT_DEPLOY_KEY` becomes `secrets.DOCKER_DEPLOY_KEY`, and
   `DEPLOY_HOST` / `SERVICE_URL` become repository **variables**
   `vars.DOCKER_DEPLOY_HOST` and `vars.SERVICE_URL`. A lab hostname is not a
   credential; it is an identifier already visible in `TEAM-STATE.md`, and
   modelling it as a variable buys back the log legibility the deploy step
   currently lacks. This follows hearthgate's convention, and the value shape
   must be specified when it is created because the two repos disagree: this
   workflow hardcodes `deploy@$DEPLOY_HOST` while hearthgate's variable carries
   the whole target with no user prefix. A wrong-shaped non-empty value passes
   an emptiness check, so the preflight cannot catch this one.

5. **A post-deploy digest readback** if and only if Decision 3 confirms the
   `get-digest` verb exists: re-run it after deploy and compare against what was
   pushed. Without this, "the slot pulled the right image" is a checklist item
   that gets ticked whenever ssh exits zero.

**Explicitly not in Slice A:** any change to the deploy shell's other rough
edges (`StrictHostKeyChecking=no`, unquoted expansions, `curl -k`, the
60-second health budget, `get-digest || echo "none"` swallowing the one
diagnostic). They are real and they are recorded as follow-ups. Changing them
in the same commit as the repair makes the first newly reachable run harder to
attribute.

## 3. Slice B, the application

Not in this round. Filed as its own issue if Decision 1 is approved.

- **D4 first**, and it is small: decide where `SESSION_SECRET` comes from.
- **D3 second**, and it is not small: a concrete `AuditRepository` against
  durable storage, plus the startup reconciliation pass
  (`contracts.py:259-261` requires closing every non-terminal attempt as
  `outcome_unknown`), factory wiring, and tests against real storage rather
  than the field-backed mock codex-worker rejected in round 3.

Both carry decisions the team does not get to make alone. The storage-backend
choice is a dependency decision and the session-secret location is a
credential-store design question, and the constitution routes both to the
principal.

## 4. Decisions for the principal

Each has a default and the consequence of no approval. None is buried in a
runbook step.

**Decision 1: split the round, and close #4 on Slice A.**
Recommended: yes. Criterion two is unreachable by any workflow change (D3, D4).
Slice A gets criterion one and is blocked on nothing else. Slice B is a day or
two and carries escalations of its own. If no: #4 stays open until the app work
lands, and the team is not able to say when.
*Against silent deferral:* a deferral without a filed slice decays into a
`TEAM-STATE.md` line, which is exactly how the D2 secrets item got lost between
round 3 and now.

**Decision 2: the deploy-key identity, and the host/URL configuration.**
Needed: confirmation that `DOCKER_DEPLOY_KEY` is the `vcf-mcp` slot's key,
and creation of `DOCKER_DEPLOY_HOST` and `SERVICE_URL` as repository variables.
The evidence that it is the right key is that it was created for this repo on
2026-07-20 and that hearthgate uses an identically-named secret for the same
host, which makes it the naming convention rather than a coincidence. That
raises confidence; it is not a fact. If it is not the right key, provision the
correct one under an explicitly agreed name and the workflow keeps that name.
Values never enter the repo, a commit, or a transcript.
*If no:* Slice A cannot merge. The preflight would fail the run by design,
which is the correct behavior but not a deploy.

**Decision 3: what the deploy key can actually run.** A read-only question to
lab-admin: does `vcf-mcp get-digest` exist, and does the key accept a bare
image reference, or is this a hearthgate-shaped general shell key expecting a
compose file. This is the round's largest unattested assumption (D5).
*If it is the hearthgate shape:* Slice A grows a compose file, a slot volume
layout, and a deploy step rewritten around `docker compose`, and roughly
doubles. That is worth discovering before the merge rather than during it.

**Decision 4: may `round/*` branches push images to GHCR?**
Recommended: yes, and it is vetoable at no cost. Benefit: the permissions fix,
package creation, visibility, and repo linkage all get proven on the round
branch instead of on `main`, and the sibling already operates this way
(hearthgate's `build.yml` triggers on `round/*` and pushes on every non-PR
event). Cost, stated plainly rather than smuggled in as a testability win: the
private package accumulates images built from code that has not passed the
round PR's external review.
*If vetoed:* keep one `deploy` job, ship the permissions block and the preflight
unchanged, and accept that the first real exercise is on `main`. That fallback
is today's behavior plus the fix, so a veto costs the round nothing it has.

**Decision 5: where does `SESSION_SECRET` come from?** **Raised now, answered
when Slice B is filed. Not blocking Slice A, and deliberately not in `TLDR.md`,
which carries only what blocks progress today.** It is listed here because it
is a design call rather than an implementation detail, and because it would
otherwise be discovered mid-implementation by whoever owns Slice B.
Option A: a slot-supplied env value, which makes lab-admin a standing
dependency on every deploy. Option B: generate on first boot and persist to
`/keys/session_secret` at 0600, with an explicit env override retained.
`/keys` is already a declared volume (`Dockerfile:29-31`), so the secret
survives restarts and admin sessions do not silently invalidate on every
deploy, and a non-writable `/keys` still raises, preserving the fail-closed
posture. The team leans B and does not decide it.

**Not on this list, deliberately: package visibility.** D6's measurement says
the docker.int host is already authenticated for a private sibling package, so
the default action is to confirm that credential's scope covers the new
package, which is a read-only question. It becomes a decision for the principal
only if that confirmation comes back negative.

## 5. What the round did not settle

- D5, by construction. It needs an attestation the round was not permitted to
  obtain.
- Whether the docker.int GHCR credential is org-scoped (in which case the new
  package is already pullable) or per-package. Read-only, and it is the first
  thing Slice A's runbook asks.
- Whether the `build` job's push actually links the package to this repository.
  A `GITHUB_TOKEN` push from the owning repo is linked on that basis, but the
  round did not prove it, and the `org.opencontainers.image.source` label
  agy-worker proposed is worth keeping as belt-and-braces for a future PAT
  push. Its stated justification (that the label affects visibility
  inheritance) is wrong and is corrected here so a later reader does not
  inherit it: labels are metadata, visibility is package settings.
