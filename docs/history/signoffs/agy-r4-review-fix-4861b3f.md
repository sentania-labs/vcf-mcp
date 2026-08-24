---
reviewed_branch: codex/r4-review-fix
reviewed_sha: 4861b3f813b3b182ad4453951fa6db298b617719
reviewed_by: agy-worker
authored_by: codex-worker
timestamp: 2026-07-27T12:23:45Z
tests_run: docker build -t vcf-ops-mcp-readonly-check . && docker run --rm --read-only -v $(pwd)/tmp_data:/data -v $(pwd)/tmp_keys:/keys -v $(pwd)/tmp_audit:/audit vcf-ops-mcp-readonly-check
result: signed-off
---

I verified the fix empirically by building the image and running it with `--read-only` and the three volumes (`/data`, `/keys`, `/audit`) mounted as specified in `deploy/compose.yml`.

The container successfully got past any startup file-system issues and failed at the application layer as expected with `RuntimeError: SESSION_SECRET must be set for production session encryption`. Running the container with a dummy `SESSION_SECRET` also successfully reached `Application startup complete.` and started listening on port 8000 without crashing due to a read-only filesystem.

The diff is clean, only containing the `read_only: true` addition. There are no em-dashes and no secret values introduced.
