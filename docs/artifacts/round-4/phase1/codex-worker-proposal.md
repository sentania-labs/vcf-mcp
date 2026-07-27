---
source-ref: c155894
source-commit: c1558944b00c180d4f6489504497368cbc9b2cc0
source-blob: 46fad1db40a38800d0faf8b6e998accd90d80f78
source-path: docs/proposals/4/codex-worker-proposal.md
worker: codex-worker
round: round-4
phase: phase1
captured: 2026-07-27
---

# Codex worker proposal: deploy permissions and first-deploy proof

## 1. Approach

I would make the eventual workflow change deliberately small, but not pretend
the permission change is the whole deployment repair. The repository currently
has no `vcf-ops-mcp` organization package, the failed main run never entered
the deploy step, the public health endpoint returns 503, and repository secret
metadata lists only `DOCKER_DEPLOY_KEY`. The workflow instead reads
`DOCKER_INT_DEPLOY_KEY`, `DEPLOY_HOST`, and `SERVICE_URL`. A permission-only
merge would therefore move the failure downstream rather than meet the issue's
acceptance criteria.

The exact workflow diff I recommend after the configuration gate is:

```diff
 jobs:
   deploy:
     name: Build & Deploy
     needs: test
     runs-on: [self-hosted]
     if: github.ref == 'refs/heads/main' && github.repository == 'sentania-labs/vcf-ops-mcp'
+    permissions:
+      contents: read
+      packages: write
     steps:
 ...
         env:
-          DEPLOY_KEY: ${{ secrets.DOCKER_INT_DEPLOY_KEY }}
+          DEPLOY_KEY: ${{ secrets.DOCKER_DEPLOY_KEY }}
```

The deploy job alone gets `packages: write`. This is preferable to the
Hearthgate workflow-level pattern here because this workflow has a separate test
job that never publishes a package. Giving the test job package creation rights
increases the authority of dependency installation and test execution for no
benefit. Job-level permissions also make every unlisted deploy-job permission
`none`, while retaining the `contents: read` needed by checkout.

The secret-name correction reflects current repository metadata, but it must be
confirmed against the slot onboarding record before implementation. If
`DOCKER_DEPLOY_KEY` is not the `vcf-ops-mcp` forced-command key, the safe fix is
to provision a correctly named repository secret and retain that confirmed name
in the workflow. The value must never be printed. `DEPLOY_HOST` and
`SERVICE_URL` must be provisioned before merge, or replaced with an agreed
non-secret configuration mechanism. Current absence is a hard pre-merge gate.

I would not rename the file or workflow in this repair. Main currently has no
branch protection or required check references, so the workflow display-name
rename is unlikely to break a gate, and the job names would remain unchanged.
It still adds an unrelated variable while diagnosing a path that has never run.
Rename both after the first green deployment, in a label-only change.

Verification is an ordered runbook with explicit failure signals:

1. **Static diff and policy check.** Confirm the eventual commit changes only
   the permission block and the confirmed deploy-key reference. Parse the YAML
   with the repository's normal workflow validation and scan the diff for an
   em-dash or secret value. A parse error, broader token permission, unexpected
   file change, or secret material stops the merge.
2. **Pre-merge repository configuration gate.** Read repository metadata and
   verify the selected deploy-key secret, `DEPLOY_HOST`, and `SERVICE_URL`
   exist. Confirm with the slot owner that the forced-command key belongs to
   `vcf-ops-mcp`, that the host accepts the documented `get-digest` and deploy
   command forms, and that it can authenticate to pull the package in the
   visibility state the first push will create. Missing names, an unconfirmed
   key, an unsupported command form, or no GHCR pull path stops the merge.
3. **Pre-merge application check.** Build the candidate image locally, start it
   with synthetic runtime configuration and temporary writable volumes, and
   require its local `/healthz` to return 200. This proves the image can start
   independently of GHCR, SSH, and fleet-caddy. A build failure, crash, or
   local 503 is an application or image failure, not a deployment-permission
   failure.
4. **Main-only workflow observation.** Merge once the gates pass, then watch
   the exact main run. Require the test job, GHCR login, and build-and-push step
   to succeed in order. A push denial means the token permission or organization
   package policy remains wrong. Record the run URL and immutable commit SHA.
5. **Package proof before interpreting deploy.** Read the created package
   metadata and confirm repository linkage, visibility, and the digest emitted
   by `docker/build-push-action`. Require the slot deploy step to pull that
   digest, not merely accept an SSH command. A missing package, unexpected
   linkage or visibility, or registry authentication failure is a packaging
   failure even if the push itself was green.
6. **Slot and rollback proof.** Require the deploy step to capture the prior
   digest, invoke the forced command, and complete its health loop. If health
   fails, verify the log reports either rollback to the prior digest or the
   explicit no-prior-digest first-deploy condition. An SSH rejection,
   malformed forced command, image pull failure, container startup failure, or
   exhausted health loop keeps the run red.
7. **Independent acceptance check.** After the run is green, execute
   `curl -k -sS -o /tmp/vcf-ops-health.json -w '%{http_code}\n'
   https://vcf-ops-mcp.int.sentania.net/healthz`, require `200`, and retain the
   non-secret JSON response. Check that the deployed slot digest equals the
   run's image digest. A 503, other non-200 response, or digest mismatch fails
   acceptance even if GitHub Actions is green.
8. **Closing evidence.** Post the main run link, commit SHA, image digest,
   package visibility/linkage result, deployed digest match, and timestamped
   health command plus response. Do not include secret values, SSH material, or
   registry credentials.

## 2. Risks

The largest risk in my approach is that it expands a purported three-line fix
into a configuration gate that requires the slot owner. That delays the merge
even if the missing secret names are merely stale metadata or an intentional
late-provisioning step. I think the delay is justified because GitHub resolves
an absent secret to an empty value, which would make the first newly reachable
deploy step fail.

The first package's pull contract is still unknown. The repository is public,
but that does not prove the first organization container package will be
public, linked as expected, or pullable by the slot host. Making the package
public manually would be a state-changing workaround and is outside this
round. The slot should instead have an established authenticated pull contract,
or the owner should explicitly approve package visibility as deployment
configuration before the merge.

The deploy shell has never run. Its use of `StrictHostKeyChecking=no`, unquoted
URL and host expansions, a 60-second health budget, `curl -k`, and
`get-digest || echo "none"` all reduce diagnostic or security quality.
Changing all of them in the permission repair would make the one main-only test
harder to attribute. The workplan should capture follow-ups, while the
pre-merge slot-contract confirmation must rule out command-shape failures.

First deployment has no rollback image. If the new container starts but is
unhealthy, the workflow can report only that no prior digest exists and leave
the endpoint unavailable. The current endpoint is already 503, so this does not
degrade a running service, but it means the stated rollback behavior is not
actually available on attempt one.

Job-level permission placement departs from the known Hearthgate pattern. A
future step moved from `deploy` into `test` would not inherit package write,
which is intentional but may surprise a maintainer. Conversely,
workflow-level placement is simpler and already proven in a sibling repository.

If I had one hour and one question, I would ask the slot owner: "What exact
GHCR credentials, package visibility assumption, forced-command grammar, and
repository secret names constitute the onboarded `vcf-ops-mcp` slot contract?"
I would spend the hour comparing that answer, read-only, with the workflow and
repository metadata. That single answer resolves the most likely failures
after the push.

## 3. Division-of-labor claim

I am best suited to own the CI security and evidence slice: least-privilege
permission placement, repository metadata checks, main-run step attribution,
package linkage and visibility proof, and a secret-safe closing evidence
template. I should not own the slot contract attestation. The resident who
authored or directly verified the forced-command deployment model is better
placed to validate command grammar, pull authentication, and rollback behavior.

## 4. Rough estimate

The workflow edit, static validation, and evidence template are roughly two
hours. Read-only configuration reconciliation with an available slot owner is
another one to two hours. The main-only run and health verification should take
under thirty minutes after merge.

The estimate grows to one or two days if the slot lacks GHCR pull credentials,
the package needs an approved visibility or linkage change, required repository
configuration is not provisioned, the forced-command grammar differs from the
workflow, or the container fails its local health check. Each is a separate
repair and should not be disguised as another blind main merge.
