---
reviewed_branch: agy/r3-delivery
reviewed_sha: 11b0227e9dd22ccc7bf44330d4a97ab077684b3a
reviewed_by: codex-worker
authored_by: agy-worker
timestamp: 2026-07-26T01:03:12Z
tests_run: "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --no-project --with 'mcp>=1.2.0' --with jinja2 --with python-multipart --with itsdangerous pytest -p no:cacheprovider"
result: changes-requested
---

# Re-review result

Changes requested. Four of the five required Tier 1 outcomes are substantively
closed, but cleanup deleted eleven files that predated this slice and
`git diff --check 19efb0c..11b0227` reports six trailing-whitespace errors.
Both are required Tier 1 items and block sign-off.

## Tier 1

### 1. PARTIALLY CLOSED: unrelated artifacts

The cleanup removed all 45 unrelated files introduced by `19efb0c`, totaling
4,209 added lines relative to the pre-slice baseline `33bca5d`. This includes
the patches, logs, diff, scratch proposals, worker markers, and other dispatch
artifacts named in the first review.

The cleanup also deleted eleven files that already existed at `33bca5d`:

```text
.team/markers/orchestrator-run-20260720-223456-end.md
.team/markers/orchestrator-run-20260720-223456-start.md
.team/markers/orchestrator-run-20260720-224036-end.md
.team/markers/orchestrator-run-20260720-224036-start.md
.team/markers/orchestrator-run-20260720-231633-end.md
.team/markers/orchestrator-run-20260720-231633-start.md
.team/markers/stale/agy-DUPLICATE-proposal-77c681e.md
.team/markers/stale/r1p1-agy-20260720-224217-start.KILLED-DUPLICATE.md
.team/markers/stale/r1p1-claude-20260720-224213-start.KILLED-DUPLICATE.md
.team/markers/stale/r1p1-codex-20260720-224215-start.KILLED-DUPLICATE.md
.team/markers/vom-r2-esc-20260721-171423-start.md
```

Those deletions are not cleanup of material introduced by this slice. Restore
the eleven baseline files while keeping the 45 slice-local artifacts removed.

### 2. CLOSED: lab identifiers moved to Actions secrets

The workflow now takes `DEPLOY_HOST` and `SERVICE_URL` from Actions secrets.
The current file contains none of `sentania.net`, `vcf-lab`, or `docker.int`.
A scan of the current workflow confirms that the previous literal FQDNs occur
only on removed diff lines.

### 3. CLOSED: literal login and session secrets fail closed

`post_login` now returns an explicit 501 response and cannot authenticate any
password. The literal `"admin"` comparison is gone. `create_app` reads
`SESSION_SECRET` and raises `RuntimeError` when it is absent. The fixed
`change_me_in_production_from_env_var` value is gone. This is the allowed
unmistakable fail-closed alternative for this increment.

### 4. OPEN: trailing whitespace

The required command is not clean:

```text
$ git diff --check 19efb0c..11b0227
.team/markers/r3-delivery-20260725-234637-end.md:20: trailing whitespace.
.team/markers/r3-delivery-20260725-234637-end.md:23: trailing whitespace.
.team/markers/vom-r3-fix-delivery-20260726-005457-start.md:11: trailing whitespace.
.team/markers/vom-r3-fix-delivery-20260726-005457-start.md:16: trailing whitespace.
src/vcf_ops_mcp/app.py:60: trailing whitespace.
tests/test_admin.py:23: trailing whitespace.
```

### 5. CLOSED: self-hosted runner model

Both workflow jobs use `runs-on: [self-hosted]`. No current
`ubuntu-latest` value remains.

## Tier 2

### Local auth-source wire value: PARTIALLY CLOSED

The endpoint now separates label and value and emits the exact local wire value
`LOCAL`, with tests. Target registration still returns 501, never reads an
auth-source value, and never sends an authentication request, so the complete
wire path remains open.

### Durable `/healthz` count: PARTIALLY CLOSED

An injected repository still supplies the count through the protocol. When no
repository exists, `/healthz` now returns 503 with
`"error": "Audit repository is unavailable"` instead of a plausible zero.
That honestly closes the misleading fallback. Production composition still
constructs no durable repository, so the durable count is not wired.

### Structural fail-closed admin writes: PARTIALLY CLOSED

`StructuralAuditMiddleware` now fails the current `/admin/targets` write closed
when audit is absent or unwritable, and the test covers that route. The
security-write set remains a local hard-coded path list inside `dispatch`,
without route metadata or an enumeration test proving all security writes are
covered. Future routes can still be omitted manually.

### Real session rotation: PARTIALLY CLOSED

Initialization and rotation now generate a new `session_id`, in addition to a
new CSRF token. There is no working login and no test proving a pre-login
session identifier changes at successful authentication, so record 004's login
rotation requirement is not closed end to end.

### Deploy prior digest and rollback: PARTIALLY CLOSED

The workflow captures a prior digest and uses that value for rollback. It does
not validate the captured value as a digest, treats any failed capture as
`none`, and only comments that fleet-caddy preserves volumes. Slot integration
also remains externally blocked, so the rollback behavior has not run.

### Volume declarations: CLOSED

The Dockerfile now declares distinct `/data`, `/keys`, and `/audit` volumes.

## Tier 3

### Record 004 remaining clauses: OPEN

The prior clause matrix remains open except for the fail-closed literal-secret
fix and the partial session work above. Bootstrap file import, scrypt-backed
credential storage, username comparison, cookie flags, logout clearing,
external `next` rejection, complete route protection, form-wide CSRF
enumeration, and the named recent-reauth operations are not implemented.

### Request-local identity: OPEN

The contracts still define `RequestIdentity` and extraction, but `create_app`
mounts FastMCP without API-key middleware or per-request identity resolution.
There is no same-session changed-key test.

### `NO_PAYLOAD` delivery serialization: OPEN

The contract and its unit tests still exist, but delivery has no response
serialization point that omits `NO_PAYLOAD` while preserving literal `None`.

## Previous claims and regression checks

1. Local auth-source wire value: PARTIALLY CLOSED, as detailed above.
2. Record 004 coverage: PARTIALLY CLOSED only for the explicit fail-closed
   credential behavior and session helper additions. Most clauses remain open.
3. Structural admin-write gating: PARTIALLY CLOSED.
4. Durable health count: PARTIALLY CLOSED.
5. No direct persistence-schema reach-through: CLOSED and not regressed.
   Delivery still uses only the `AuditRepository` protocol and contains no
   persistence schema access.
6. `NO_PAYLOAD` serialization: OPEN.
7. CI and deploy semantics: PARTIALLY CLOSED. Secret indirection and
   self-hosted runners are closed; rollback mechanics remain partial. Stub
   checks are now honestly named incomplete.
8. Packaging cleanliness and volumes: PARTIALLY CLOSED. Volumes, host
   indirection, and literal-secret cleanup are closed, but baseline marker
   deletion and whitespace remain.
9. Scope honesty and stubs: PARTIALLY CLOSED. Login and target registration
   now return explicit unavailable responses, missing audit composition is
   unmistakable, and CI stubs are labelled incomplete. The cleanup overreach
   remains.
10. Request-local identity: OPEN.

The previously confirmed absence of direct persistence-schema reach-through did
not regress. The delivery diff adds no forbidden dash characters. No real
credentials were found.

The security-critical placeholders that looked operational are gone from what
remains: login and target registration explicitly return 501, missing audit
composition returns an unmistakable 503, missing session secret aborts startup,
and incomplete CI checks are labelled incomplete. This statement does not mean
the Tier 2 or Tier 3 security work is implemented.

## Test output

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-agy
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 20 items

tests/test_admin.py .....                                                [ 25%]
tests/test_app.py ..                                                     [ 35%]
tests/test_auth.py ......                                                [ 65%]
tests/test_contracts.py .......                                          [100%]

=============================== warnings summary ===============================
tests/test_admin.py:9
  /home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-agy/tests/test_admin.py:9: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient

======================== 20 passed, 1 warning in 1.32s =========================
```

## Required next increment

Restore the eleven files that predate the delivery slice and remove the six
trailing-whitespace errors. The other Tier 2 and Tier 3 items remain the next
planned implementation work and do not independently block this tiered
re-review.
