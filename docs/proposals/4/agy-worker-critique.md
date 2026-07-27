# Critique of Phase 1 Proposals

## 1. Where `permissions:` goes
**Steelman for Claude-worker:** Putting `permissions:` at the workflow level applies a straightforward, centralized configuration that matches known-good patterns like `hearthgate`, reducing the risk of missing it if jobs are refactored.
**Steelman for Codex-worker:** Scoping `permissions:` strictly to the `deploy` job adheres to least privilege, avoiding giving `packages: write` to the `test` job.
**Critique:** Claude's argument that workflow-level `permissions` is a net reduction for the `test` job is factually wrong. Running `gh api repos/sentania-labs/vcf-ops-mcp/actions/permissions/workflow` confirms the repo's `default_workflow_permissions` is `read`. Therefore, the `test` job currently runs with only `contents: read`. Adding `packages: write` at the workflow level actively expands the `test` job's permissions for no reason. Codex is correct here; the permissions must be scoped strictly to the `deploy` job.

## 2. The missing secrets
**Steelman for Claude-worker:** Adding a preflight step to loudly check for required secrets (`DEPLOY_HOST`, `SERVICE_URL`, `DOCKER_DEPLOY_KEY`) prevents the workflow from failing silently or executing malformed SSH commands.
**Steelman for Codex-worker:** Verifying the secrets with the slot owner before merging is a necessary gate, and matching the workflow to the only existing secret (`DOCKER_DEPLOY_KEY`) resolves the immediate mismatch.
**Critique:** Both peers correctly identified that three secrets are missing and only `DOCKER_DEPLOY_KEY` exists. However, both propose renaming `DOCKER_INT_DEPLOY_KEY` to `DOCKER_DEPLOY_KEY` in the workflow *before* confirming if that is actually the correct key for this slot. Codex mentions confirming it pre-merge, but still includes the rename in its proposed diff. Claude's preflight step is a superior mechanical safeguard because it explicitly halts the pipeline with a readable error if the dependencies aren't met, rather than relying on silent empty variables during SSH. I side with Claude's preflight logic, but agree with Codex that the secret names must be explicitly confirmed by Scott pre-merge before we change the code to use them.

## 3. Whether `/healthz` can return 200 at all
**Steelman for Claude-worker:** Claude correctly proves via source code inspection that `uvicorn` calls `create_app` with no arguments, defaulting `AuditRepository` to `None`, which structurally forces `/healthz` to return 503.
**Steelman for Codex-worker:** Codex includes a rigorous local pre-merge check to ensure the application starts correctly before trusting the CI deployment.
**Critique:** Codex's proposal completely misses the structural defect in `app.py`. Codex's Step 7 mandates we "require 200" from the deployed health check, but this is impossible without application changes. Claude correctly identifies that Acceptance Criterion 2 cannot be met by this workflow fix alone and proposes splitting the work into Slice A (workflow) and Slice B (app). Claude is entirely correct here; pretending a YAML permission fix will result in a 200 from `/healthz` is setting the round up for failure.

## 4. The build/deploy job split
**Steelman for Claude-worker:** Splitting the `deploy` job into a `build` and `deploy` job allows us to test the image push step on round branches before merging to `main`, buying us a valuable test loop.
**Steelman for Codex-worker:** Keeping the job structure exactly as-is minimizes the surface area of untestable YAML changes on a sensitive deployment script.
**Critique:** Claude's proposal to split the job introduces a cross-job dependency (`needs.build.outputs.digest`) that they admit is untested. If `$GITHUB_OUTPUT` fails to pass the digest across the job boundary, the deploy job will SSH a bare image reference and fail on `main`. This is exactly the kind of untestable logic we are trying to avoid. Codex is correct to keep the diff as small and localized as possible. We shouldn't redesign the workflow structure and risk breaking the pipeline state just to test a one-line permission fix.

## 5. The rename
**Steelman for Claude-worker:** Renaming the workflow file is safe because there are no branch protection rules or other automation relying on the name `ai-log-depot`.
**Steelman for Codex-worker:** Deferring the rename removes an unrelated variable from a critical path repair, saving it for a label-only change after we achieve a green deploy.
**Critique:** Claude's proposal bundles a cosmetic rename into a critical deployment fix. If the workflow fails to trigger or behaves unexpectedly on `main`, we'd have to investigate whether the rename broke something. Codex's approach to defer the rename until after the first successful deploy is the safer, more professional path.

## 6. What Scott is actually being asked to approve
**Steelman for Claude-worker:** Claude surfaces the architectural decision of where `SESSION_SECRET` should live (persisted `/keys` volume vs slot env) and explicitly asks for a decision on whether to split the issue scope.
**Steelman for Codex-worker:** Codex lists explicit questions for the slot owner regarding the GHCR pull credentials, visibility assumptions, and the forced-command grammar.
**Critique:** Both peers successfully surface decisions that require the principal's input, avoiding making assumptions that could break the org or architecture. Claude correctly escalates the scope split (Slice A vs Slice B) and the secret storage architecture. Codex correctly escalates the package visibility and SSH forced-command contract. A complete workplan must merge both sets of escalations: asking Scott to approve the scope split, confirm the SSH forced-command grammar, and provision the missing secrets/visibility. Both did a good job here, but Codex's failure to catch the 503 issue means its escalations are incomplete.
