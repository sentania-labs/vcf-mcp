# Proposal: Round 4 (Deploy Permissions)

## 1. Approach

1. **Scope the Permissions**: Add the `permissions` block strictly to the `deploy` job, not the workflow root. The `test` job does not need package write access, so we practice least privilege.
2. **Repo Linkage**: Add the `org.opencontainers.image.source` label directly via the `docker/build-push-action` step in the workflow. A first-time GHCR push via `GITHUB_TOKEN` creates the package unlinked in the org namespace. Explicitly linking it ensures it is tied to this repository, which is required for repository-level access control and visibility inheritance.
3. **Cosmetics**: Rename `name: ai-log-depot` to `name: vcf-mcp` and rename the file `ai-log-depot.yml` to `vcf-mcp.yml`. Recon confirms no branch protection rules or `consensus.yml` jobs depend on the old name.

**Diff applied to `.github/workflows/ai-log-depot.yml` (prior to rename):**
```yaml
--- .github/workflows/ai-log-depot.yml
+++ .github/workflows/vcf-mcp.yml
@@ -1,4 +1,4 @@
-name: ai-log-depot
+name: vcf-mcp
 
 on:
   push:
@@ -45,6 +45,8 @@
     needs: test
     runs-on: [self-hosted]
     if: github.ref == 'refs/heads/main' && github.repository == 'sentania-labs/vcf-mcp'
+    permissions:
+      contents: read
+      packages: write
     steps:
       - uses: actions/checkout@v4
 
@@ -62,6 +64,8 @@
         with:
           context: .
           push: true
           tags: ghcr.io/sentania-labs/vcf-mcp:${{ github.sha }}
+          labels: |
+            org.opencontainers.image.source=https://github.com/sentania-labs/vcf-mcp
```

**Verification Steps (Post-Merge):**
- **Step 1:** Observe the `Build and push image` step in GitHub Actions on `main`. It will succeed due to the added permissions block.
- **Step 2:** The pipeline moves to the `Deploy to slot and verify health` step, executing `ssh ... ghcr.io/sentania-labs/vcf-mcp@<DIGEST>`.
- **Step 3 (The Catch):** If the deploy host (`$DEPLOY_HOST`) pulls anonymously, this step will fail with `unauthorized` or `ImagePullBackOff` because a newly minted GHCR org package defaults to Private visibility. If this occurs, a human (Scott) must manually change the package visibility to Public in GHCR settings and re-run the failed job.
- **Step 4:** Once the image is pulled, the workflow loops waiting for `/healthz` to return 200. We observe the workflow log to confirm the health check succeeds and exits 0.

## 2. Risks

- **Package Visibility (The primary break point):** The issue asserts the permissions block is the *only* thing between merged code and a running service. This is likely false. The first push of a new package to an org creates it as Private. If the multi-tenant `$DEPLOY_HOST` pulls anonymously, the deploy step will immediately fail with an authentication error. If I had one hour and one question, it would be: "Does the `deploy` user on `$DEPLOY_HOST` have a `.docker/config.json` with a PAT authorized to pull private GHCR packages from `sentania-labs`, or is the lab policy that packages must be manually flipped to Public?"
- **Digest vs Tag execution:** The deploy step passes `${IMAGE_DIGEST}` (which resolves to `sha256:abcd...`) to the remote `vcf-mcp` command. If the remote wrapper script parses this expecting a plain tag rather than a digest hash, it will fail. However, standard Docker/Containerd tools natively accept `image@sha256:...`, making this risk low.
- **Health check timeout:** The deploy step waits 60 seconds (12 loops of 5s) for the app to return 200 from `/healthz`. If the app takes longer to boot on a cold start, the pipeline will roll back and fail, even if the deployment was fundamentally sound.

## 3. Division-of-labor claim

I (agy-worker) should own this implementation. While adding the `permissions` block touches CI security (Codex's domain), the real complexity and risk of this round lie in the slot deployment model and the behavior of the `$DEPLOY_HOST` when it encounters a newly minted GHCR package. Because I authored the deploy job and own the slot model, I am best positioned to interpret the deploy step's failure modes and adapt the script if the digest parsing or SSH commands require adjustments after the first run.

## 4. Rough estimate

Less than 10 minutes to write the commit and merge the PR. However, proving the acceptance criteria requires a post-merge run. If the package defaults to Private and `$DEPLOY_HOST` lacks credentials, the job will fail. This requires a human to manually change the GHCR package visibility to Public and re-run the job, adding however long it takes the admin to click the button.
