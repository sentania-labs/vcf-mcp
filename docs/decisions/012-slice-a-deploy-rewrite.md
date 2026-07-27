# 012: Slice A is a compose-shaped deploy rewrite, not a permissions patch

- **Status:** accepted
- **Round:** 4, execution phase (issue #4)
- **Workers dispatched:** codex-worker, agy-worker
- **Supersedes:** nothing. Extends `011-deploy-path-repair.md` with the
  answers to the five decisions that record left open.
- **Protected paths touched:** `.github/workflows/` (Slice A)

## Context

Round 4 delivered a spec and a workplan and put five decisions to the
principal. The principal answered `approved` on issue #4 with no
per-decision guidance. Per keystone rule 5 the orchestrator resolves them
rather than asking again, and per keystone rule 4 the bar is the described
use case working.

Four of the five are answerable from read-only evidence on this box. This
record is that evidence and the resulting rulings, so the round does not
re-derive them.

## Decision 1: split the issue. Approved as recommended.

Issue #4 keeps Slice A (the CI/deploy path) and closes on it. Slice B (the
application defects behind the permanent 503) is filed as issue #5 and is
claude-worker's, codex-worker reviewing, per the division of labor in 011.

Rationale: Slice A is hours, Slice B is days and needs a durable audit store
that does not exist. Holding #4 open across both keeps a completed CI repair
invisible for a week.

## Decision 2: the two missing configuration values are repository variables.

Created by the orchestrator at 2026-07-27T11:37:00Z:

| Name | Value | Kind |
| --- | --- | --- |
| `DOCKER_DEPLOY_HOST` | `deploy@docker.int.sentania.net` | variable |
| `SERVICE_URL` | `https://vcf-ops-mcp.int.sentania.net` | variable |

Neither is a credential, so neither is a secret.

**The shape question is settled in favor of hearthgate's convention:
`DOCKER_DEPLOY_HOST` carries the full `user@host`.** hearthgate's variable is
literally `deploy@docker.int.sentania.net` and its workflow passes it to `scp`
and `ssh` with no prefix. This workflow currently hardcodes `deploy@$DEPLOY_HOST`,
which against the same value produces `deploy@deploy@docker.int.sentania.net`.
**Slice A therefore drops the hardcoded `deploy@` prefix.** Two repos deploying
to the same host under two different conventions is the silent failure round 4
predicted; one convention wins and it is the one already in production.

## Decision 3: the deploy key is a forced-command wrapper with no `get-digest` verb. Slice A doubles.

This is the decision that landed badly, and it is settled from source rather
than from inference. `~/claude/lab-admin/scripts/deploy-wrapper.sh` is the
forced command behind every slot key on `deploy@docker.int`. It takes the slot
name from `authorized_keys` as `$1`, validates `SSH_ORIGINAL_COMMAND` against a
closed verb list, and denies anything else. The allowed verbs are:

- `scp -t /srv/services/<slot>/...`
- `scp -t /srv/fleet-caddy/conf.d/<slot>/<slot>.{json,caddy}`
- `rm -f /srv/fleet-caddy/conf.d/<slot>.caddy`
- `docker compose --project-directory /srv/services/<slot> {pull|up -d|down|ps|restart|logs}`

`vcf-ops-mcp get-digest` is not in that list and never was. It appears nowhere
outside this repo's own workflow file. Every ssh in the current deploy step
would be denied and logged.

**Ruling: Slice A rewrites the deploy step around a compose file, hearthgate-shaped.**
The deploy step ships `docker-compose.yml` and a generated `.env` pinning the
image by digest into `/srv/services/vcf-ops-mcp/`, then runs `pull`, `up -d`,
`ps`. Digest pinning survives because `.env` is a file the wrapper lets us
upload, not a verb it has to understand.

Rollback loses its `get-digest` source. It is re-derived from
`docker compose ps`-visible state, or it is dropped for the first deploy and
recorded as a follow-up, at the implementer's discretion. A first-ever deploy
has nothing to roll back to regardless.

**On whether `DOCKER_DEPLOY_KEY` is this slot's key:** unverifiable read-only,
because secret values are not readable and direct ssh to lab hosts is
forbidden. It does not need to be verified in advance. The wrapper derives the
slot from `authorized_keys`, so a wrong key produces
`deploy-wrapper: command not allowed` on the first scp: loud, immediate,
attributable, and harmless. That is a better oracle than an attestation, and
it costs one run.

## Decision 4: yes, push images to GHCR from `round/*`. Approved.

The workflow already triggers on `push: branches: [main, "round/*"]`; only the
`deploy` job is gated to `main`. Splitting build-and-push from deploy so the
push runs on `round/*` buys a test loop instead of one blind shot per merge.
The package is private, tagged per commit, and hearthgate already does this.
The cost, images built from code that has not passed external review
accumulating in a private registry, is accepted.

## Decision 5: Slice B. Filed as issue #5, blocks nothing here.

`/healthz` returns 503 at every possible digest. **The `main` run that closes
#4 is expected to end red at the health poll, and that is the correct outcome,
not a regression to debug.** Green through build, push, and slot deploy; red at
a gate that is Slice B's acceptance test arriving early. Nobody extends the
timeout and re-runs.

## Two things round 4 could not know

- **The slot's registered `upstream_service` and `upstream_port`.** The
  onboarding contract's convention is `<slot>-web` and a container port; this
  image `EXPOSE`s 8000 and binds uvicorn there. Slice A writes the compose
  service as `vcf-ops-mcp-web` on port 8000 to match both. If fleet-caddy was
  registered against something else, the symptom is a continued 503 with a
  running container, which is distinguishable from Slice B's 503 by
  `docker compose ps`.
- **`.team/blocked/fleet-caddy-slot-config.md` is resolved.** TLS terminates
  and the proxy answers 503 rather than dying at Client Hello. Closed out this
  round.

## Dissent

None recorded at ruling time. These are orchestrator rulings on questions the
principal declined to answer, not a contested synthesis, so no ballot was
taken and the critic seat was not invoked. Doers may deny in review; a denial
that lands reopens the specific ruling it names.

## Sign-offs

Signatures in the format `tools/consensus-check.py` reads, following the
shape of `009-phase1-build-synthesis.md`. Each doer appended only its own
line, on its own branch; the orchestrator collected them here at merge and
changed no line's content. The longer per-doer ratification write-ups for
011 remain under `docs/decisions/signatures/`.

    Signed-off-by: codex-worker <codex@team.local> 2026-07-27T11:58:30Z
    Signed-off-by: agy-worker <agy@team.local> 2026-07-27T11:58:16Z
