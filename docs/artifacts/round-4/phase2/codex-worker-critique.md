---
source-ref: 6f341a1
source-commit: 6f341a11a59a2714b3d5966c42e3b26136a8ca58
source-blob: 438d4d8faf97255d15c96b7715580025ee7f0aab
source-path: docs/proposals/4/codex-worker-critique.md
worker: codex-worker
round: round-4
phase: phase2
captured: 2026-07-27
---

# Codex worker critique: Round 4 deploy permissions

## Evidence checked for this critique

I performed read-only recon against the repository and source before judging
either proposal:

- `repos/sentania-labs/vcf-ops-mcp/actions/permissions/workflow` reports
  `default_workflow_permissions: read`.
- Repository Actions secret metadata contains only `DOCKER_DEPLOY_KEY`.
  Organization secret metadata contains none of `DOCKER_INT_DEPLOY_KEY`,
  `DEPLOY_HOST`, `SERVICE_URL`, or `DOCKER_DEPLOY_KEY`.
- The workflow reads `DOCKER_INT_DEPLOY_KEY`, `DEPLOY_HOST`, and `SERVICE_URL`.
- `Dockerfile` invokes `uvicorn vcf_ops_mcp.app:create_app --factory`, so the
  factory receives no audit repository argument.
- `create_app` raises when `SESSION_SECRET` is absent. No workflow or
  repository deployment artifact supplies it.
- With a session secret present, the no-argument factory stores `None` as the
  audit repository, and `/healthz` returns 503.
- `AuditRepository` is a protocol. The only implementations found in this
  repository are test doubles. There is no concrete implementation under
  `src/`.

These checks confirm Claude's D2, D3, and D4 findings. They also disprove
Claude's workflow-level permission argument under this repository's actual
settings.

## Claude worker proposal

### Steelman

Claude's strongest argument is that the issue mistakes the first observable
failure for the complete deployment problem. Its proposal reconstructs the
whole path from package creation through slot startup and proves that a
workflow-only change cannot satisfy the stated 200 response criterion.

The build/deploy split is strongest when treated as a proposal to buy a
repeatable registry integration test on every round branch, not merely as a
way to debug this incident. Under an explicit policy allowing non-main
commit-SHA images in GHCR, that long-term feedback loop has real value.

### Attack 1: workflow-level permissions are broader, not a reduction

I am attacking Claude's workflow-level `permissions` placement. Its claim that
the block is a net token reduction for `test` depended on an unread setting.
The setting is `default_workflow_permissions: read`. Therefore the current
test job already receives the read default, while Claude's root block would
add `packages: write` to dependency installation and test execution.

The shared self-hosted runner does not make token least privilege irrelevant.
Runner compromise and misuse of the current job token are different controls.
An untrusted dependency running in `test` should not be able to create or
publish organization packages merely because a later job legitimately needs
that capability.

Claude is wrong on this point, and agy and my phase-1 proposal are right. Put
`contents: read` and `packages: write` on the package-pushing job only. The
test job can remain on the repository's confirmed read default, or receive an
explicit `contents: read` block for clarity.

### Attack 2: the build/deploy split creates an unproved boundary and a policy

I am attacking Claude's split of the existing job into `build` and `deploy`.
It adds a job-output boundary that the proposal itself admits is not exercised
on a round branch. Printing the digest inside `build` does not prove that
`needs.build.outputs.digest` reaches `deploy`. The first consumption of that
new boundary would still occur on `main`, exactly where the proposal says
untested YAML is too costly.

The split also changes package publication policy. Every pushed round branch
would publish an organization image built from code that has not passed the
round PR's external review. Commit-SHA tags and digest deployment reduce
ambiguity, but they do not answer retention, package discoverability, or who
is authorized to publish pre-integration artifacts. Calling the package
private does not make this policy free.

Do not split the job in this repair. Keep the known step-output path inside one
job and make the smallest permission and input-validation changes. If the team
wants branch image publication as a durable CI feature, specify it separately,
including package cleanup and review-state policy, then test the job-output
contract without relying on a main-only consumer.

### Attack 3: the missing-secret response is incomplete as a merge plan

Claude correctly finds all three missing secret references and correctly
demands a loud preflight. It also correctly treats the forced-command grammar
as unverified.

The costly part is that its workplan says Scott or the orchestrator creates
`DEPLOY_HOST` and `SERVICE_URL`, while treating `DOCKER_DEPLOY_KEY` as the
likely selected key. Secret-name similarity and the Hearthgate precedent do
not prove that this value is the forced-command key for the `vcf-ops-mcp`
slot. A preflight only proves non-emptiness, not identity or command
authorization.

The spec must present Scott with a decision before implementation:

1. Confirm that `DOCKER_DEPLOY_KEY` is the slot-specific forced-command key,
   then rename the workflow reference to it.
2. Otherwise provision the confirmed slot key under an explicit agreed name
   and retain that name in the workflow.

In either branch, create `DEPLOY_HOST` and `SERVICE_URL` before the main run
and add a preflight that names missing variables without printing values.
Renaming plus preflight are both necessary, but the rename is conditional on
key ownership confirmation.

### Attack 4: the application slice is correctly found but too casually owned

Claude is right that criterion two is unreachable today. I was wrong in my
phase-1 proposal to describe a synthetic local `/healthz` 200 as a pre-merge
gate without first stating that the repository has no production composition
capable of meeting it. The local check is useful only after an application
slice exists.

Claude's proposed Slice B nevertheless contains decisions that this worker
team cannot silently absorb into a workplan. Choosing durable audit storage
is an architecture and dependency decision. Generating and persisting a
session secret on first boot changes credential-store behavior. The
constitution requires escalation to the principal for architecture changes,
new dependencies, and credential-store encryption design.

The round should split at the specification level. Slice A may implement the
workflow repair and prove package push plus deploy invocation. Criterion two
must be explicitly deferred to a separately approved application/runtime
slice whose storage and session-secret decisions are presented to Scott.
Issue closure must say that 200 health is deferred, not claim full acceptance.

### Attack 5: do not combine the rename with the first deployment repair

Claude proves well that no branch protection or consensus mechanism consumes
the old check-run name. That makes the rename safe in isolation, but it does
not make it useful to this repair. The first successful main-only deployment
already has several newly exposed failure points. Changing the workflow
identity also fragments the Actions history at the moment operators most need
to compare the failed and repaired runs.

Defer the file and display-name rename until after the first green deployment
path. This is not fear of a hidden required check. It is attribution and
operational continuity. On this point I retain my phase-1 position over
Claude's.

### Attack 6: Scott's approvals need to be explicit gates

Claude does better than either other proposal at surfacing human work, but its
steps still mix decisions with execution. "Create the missing secrets" is not
one decision. Scott must approve or provide:

- the authoritative slot key name and confirmation of its forced-command
  grammar;
- the configuration location for host and service URL;
- the private-package pull contract, or an explicit package visibility
  change;
- permission, if desired, to publish round-branch images;
- the scope split that defers criterion two;
- later architecture choices for durable audit storage and session-secret
  provisioning.

These belong in the approval section of the spec, each with a default and the
consequence of no approval. They should not be buried as runbook prerequisites.

## Antigravity worker proposal

### Steelman

Agy's strongest proposal is a deliberately small, least-privilege permission
fix paired with explicit repository linkage metadata. It correctly recognizes
that first-package visibility and slot pull authentication can fail after a
successful push, and it assigns the slot behavior to the resident who authored
that model.

Its rename argument is also evidence-based: no protected check or consensus
consumer uses the old name. If the round were a general workflow cleanup
rather than a first-deployment repair, the rename would be reasonable.

### Attack 1: the plan cannot reach its stated deploy step

I am attacking agy's verification sequence. It says that after the push the
pipeline moves to SSH deployment, but all three workflow-provided inputs to
that step are absent. The only repository secret is `DOCKER_DEPLOY_KEY`; the
workflow reads `DOCKER_INT_DEPLOY_KEY`, `DEPLOY_HOST`, and `SERVICE_URL`.
Organization metadata supplies none of them.

The first prior-digest SSH failure is swallowed, then the deployment SSH fails
with an empty key and host. Package visibility is not the primary next break
point because the workflow cannot reach a meaningful pull attempt.

The replacement plan must make missing inputs a pre-merge gate, conditionally
rename the key reference only after confirming key identity, provision host
and service URL configuration, and add a loud non-secret preflight before SSH.

### Attack 2: the proposal assumes an unverified forced-command contract

Agy says standard container tools accept digest references, but that does not
answer whether the remote `vcf-ops-mcp` wrapper accepts either
`get-digest` or an image reference. The wrapper is not in this repository and
the proposal supplies no read-only evidence of its grammar. Owning the slot
model is not evidence that the deployed host matches it.

Scott or lab-admin must attest the exact forced-command interface before the
main run. If the key instead authorizes a general shell or a different command
shape, the workflow needs a newly scoped deploy design, not an after-the-fact
adaptation.

### Attack 3: the health check can never succeed

I am attacking agy's Step 4, which expects observation of a successful
`/healthz` loop. The current production entry point raises without
`SESSION_SECRET`. Nothing in the repository supplies that variable. Even if
it were supplied externally, uvicorn invokes `create_app` with no audit
repository, and that app returns 503. There is no concrete `AuditRepository`
under `src/` to wire.

This is not a timeout risk and cannot be fixed by waiting longer than 60
seconds. It makes acceptance criterion two impossible for every current image
digest. The spec must explicitly split or defer the application/runtime work,
with Scott approving the scope change and architecture decisions. Agy's
proposal would otherwise direct Scott to rerun a job that is guaranteed to
fail.

### Attack 4: the OCI source label does not settle the pull contract

The source label is a sensible way to express repository linkage, and agy is
right to care about it. But linkage, visibility, and authorization are
separate facts. Adding a label does not establish that the slot can pull a
private image, and it does not authorize changing the package public.

The workplan should retain the source label only if package metadata
verification confirms it is required, then require read-only proof of actual
repository linkage and visibility after creation. Before merge, Scott must
choose the intended pull contract: authenticated private pull or approved
public visibility. "Flip it public if it fails" is a state-changing,
security-relevant decision, not a recovery step a worker may assume.

### Attack 5: post-merge-only verification is too reactive

Agy estimates less than ten minutes to change and merge, then discovers every
material unknown on `main`. That is cheap authoring but expensive operations.
The missing configuration and command grammar are knowable before merge, and
the image's guaranteed startup/readiness failure is knowable from source now.

Keep the YAML edit small, but make configuration reconciliation, forced-command
attestation, and a local image startup check blocking workplan steps. The local
check will currently fail, which is useful evidence for the scope decision.
Do not use the main deployment run as discovery for known defects.

### Attack 6: defer the rename

Agy is right that no current check consumer blocks the rename. I still oppose
combining it with this first-deployment repair. It changes run identity and
history grouping without helping package authorization, slot invocation, or
health. Rename the workflow and file in a label-only follow-up after the
deployment path has a green baseline.

### Attack 7: Scott is asked for too little, too late

Agy surfaces package visibility as a human click after failure, but misses the
other decisions the evidence requires. Scott must approve the authoritative
deploy-key mapping, host and service configuration, forced-command contract,
private-pull versus public-package policy, and the criterion-two scope split.
The proposal should place those decisions before implementation, not ask only
for a visibility change after the first failed main run.

## Recommended synthesis

The approved workplan should use job-scoped `contents: read` and
`packages: write`, keep build and deploy in one job, defer the rename, and add
a secret-safe preflight. It should change the deploy-key reference only after
Scott or the slot owner confirms that `DOCKER_DEPLOY_KEY` is the correct
forced-command key, and it should require `DEPLOY_HOST` and `SERVICE_URL`
configuration before merge.

The plan must treat package linkage, visibility, and pull authentication as
three separately verified properties. It must also state that the current
image cannot return 200 and ask Scott to approve either a two-slice round or
explicit deferral of criterion two. Any later durable audit repository or
session-secret persistence design is an architecture decision for the
principal, not an implementation detail for this critique round.
