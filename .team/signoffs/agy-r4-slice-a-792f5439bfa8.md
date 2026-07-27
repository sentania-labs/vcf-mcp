---
reviewed_branch: codex/r4-slice-a
reviewed_sha: 792f5439bfa8ae3b4e23ee4a9d9bf1fd0f7b2517
reviewed_by: agy-worker
authored_by: codex-worker
timestamp: 2026-07-27T11:45:00Z
tests_run: none
result: changes-requested
---

Withholding sign-off due to FATAL deployment failures that violate the host contract and break the deploy step:

1. **Missing `docker-slots` network and external network declaration:** `deploy/compose.yml` does not join the `docker-slots` network, nor does it declare it as external. Per the host contract `lab-container-host-contract.md` section 3.2.2, this is mandatory. Without this, `fleet-caddy` cannot route traffic to the container, and the `/healthz` check via `$SERVICE_URL` will fail to reach the app. Fix: Add `networks: [docker-slots]` to the web service and `networks: docker-slots: { external: true }` at the root.
2. **Missing resource limits and logging capped:** `deploy/compose.yml` lacks resource limits (`deploy.resources.limits`) and logging caps (`logging.driver: json-file`, etc.). Per the host contract section 3.2.2, these are mandatory rules. Fix: Implement the resource limits and logging configuration as shown in the contract.
3. **Invalid `SESSION_SECRET` variable expansion:** `deploy/compose.yml` uses `SESSION_SECRET: ${SESSION_SECRET:?SESSION_SECRET must be set}`. Because `.env` (generated in the workflow) does not define `SESSION_SECRET`, `docker compose up -d` will immediately crash with an error that `SESSION_SECRET` must be set, breaking the deploy step entirely. The prompt explicitly instructed not to satisfy it if it's absent and to "express the requirement without satisfying it (an env key sourced from `.env`, absent for now)". The `:?` bash expansion actively breaks Docker Compose when the variable is unset. Fix: Use `${SESSION_SECRET:-}` or omit the environment variable entirely for this round.

Other checks (diff scope, secrets, em-dashes) passed.
