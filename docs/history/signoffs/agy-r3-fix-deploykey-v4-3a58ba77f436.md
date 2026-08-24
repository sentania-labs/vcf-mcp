---
reviewed_branch: agy/r3-fix-deploykey-v4
reviewed_sha: 3a58ba77f43662a48c615507e4666689d3b02565
reviewed_by: codex-worker
authored_by: agy-worker
timestamp: 2026-07-26T02:08:48Z
tests_run: pytest tests/
result: signed-off
---

This sign-off supersedes the withheld sign-offs at `106a317`, `e1ff831`,
and `2e8d353`.

I reviewed the whole fix from `e73bad5` and the final two-line iteration from
`2e8d353`. The merged change moves the deploy key into `RUNNER_TEMP`, creates
it with mode 600, uses that path for every SSH invocation, and installs an
EXIT trap that removes it on successful, failed, and rollback paths.

The final guard rejects unset and empty `RUNNER_TEMP` before `KEY_PATH` is
derived under bash. The trap body is literal, expands `KEY_PATH` when the trap
fires, and retains access to the shell variable then. An apostrophe-containing
temporary path was exercised successfully. No file other than the workflow
changed in either reviewed diff. After reproducing the CI editable install in
a temporary virtual environment, the literal CI command `pytest tests/`
completed with 124 passed and 13 skipped.
