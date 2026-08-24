---
reviewed_branch: agy/r3-delivery
reviewed_sha: 19efb0cdab604a7a6f38d5e6e512ea99ffa63c2a
reviewed_by: codex-worker
authored_by: agy-worker
timestamp: 2026-07-26T00:48:25Z
tests_run: "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --no-project --with 'mcp>=1.2.0' --with jinja2 --with python-multipart --with itsdangerous pytest -p no:cacheprovider"
result: changes-requested
---

# Review result

Changes requested. The default suite passes, but the slice does not implement
several binding delivery requirements and introduces security-critical
placeholders that look operational. The branch also contains 4,101 lines of
unrelated markers, patches, logs, diffs, and proposal scratch files.

## Required claims

### 1. DENIED: local auth-source wire value

`src/vcf_ops_mcp/admin/routes.py:56-79` returns a flat list of display strings.
The local entry is only `"Local users"` at lines 63, 72, and 79. There is no
separate display label and wire value such as
`{"label": "Local Users", "value": "LOCAL"}`.

The value cannot be traced to an authentication request because
`post_target_register` never reads `authSource`, never authenticates to the
appliance, and never saves a target. Lines 96-104 read only the CSRF token and
return a redirect. Thus this commit does not itself send the wrong label to the
appliance, but it exposes only the known-invalid label for a future form to
submit and omits the required `LOCAL` wire value entirely.

Required change: represent labels and wire values separately, make the local
entry's wire value exactly `LOCAL`, submit that value through the registration
and authentication path, and test the request received by a mock appliance.

### 2. DENIED: record 004 hardening coverage

Record 004 says the workplan has nine requirements, but its operative text at
`docs/decisions/004-admin-ui-stack.md:63-85` contains eleven independently
testable hardening clauses when compound phrases are split. Mapping every
clause avoids hiding missing coverage in the count discrepancy.

| Record 004 clause | Test | Result |
| --- | --- | --- |
| scrypt password hashing | `tests/test_auth.py:10-21`, `test_password_hashing` | Covered for round trip and wrong password, but does not pin scrypt parameters |
| constant-time username comparison | None | Missing, and no username comparison exists |
| session cleared on login and logout | `tests/test_auth.py:35-43` indirectly starts empty | Missing login clear assertion, missing logout route and test |
| signed `HttpOnly`, `Secure`, `SameSite=Strict` cookie | None | Missing; `app.py:44-46` configures none of these flags explicitly |
| external `next` targets rejected | None | Missing; `auth.py:91` stores an absolute URL and no consuming route exists |
| JSON callers receive 401 rather than redirect | `tests/test_admin.py:35-38` exercises an authenticated JSON call only | Missing unauthenticated JSON assertion; `require_auth` itself redirects |
| every management route protected | Individual happy paths only | Missing route-enumeration test; login is intentionally public, other coverage is not exhaustive |
| per-session CSRF, constant-time checked on every state-changing form | `tests/test_auth.py:103-112`, `tests/test_admin.py:80-84` | Partial; helper comparison and the only target POST are covered, but there is no form enumeration |
| session rotation at login | `tests/test_auth.py:71-78` | Denied by the test itself: it only changes CSRF after login; no session identifier is rotated and login does not call `rotate_session` |
| short idle lifetime | `tests/test_auth.py:45-69` | Covered at helper level |
| recent reauthentication before action enablement, API-key mint, and key rotation | `tests/test_auth.py:80-101`, `tests/test_admin.py:86-100` | Partial helper and target-registration test only; the three required sensitive routes do not exist |

Record 004 separately requires bootstrap import from a validated secret file,
one-time hashing into encrypted storage, invalidation, and fail-closed startup
at lines 63-69. That requirement has no implementation or test. Instead,
`routes.py:41-44` accepts the literal password `"admin"`, and
`app.py:44-46` uses the literal session secret
`"change_me_in_production_from_env_var"`.

Required change: implement the full record 004 surface and add a test for each
clause, including each sensitive operation named by recent reauthentication.

### 3. DENIED: structural fail-closed admin writes

There is no defined or enumerated security-write set. The audit check is a
manual call inside the sole `post_target_register` endpoint at
`routes.py:91-94`. A new route can omit it. `admin_routes` at lines 107-113 is
a plain list of Starlette routes with no security-write metadata, wrapper, base
endpoint, or middleware enforcing the rider.

Required change: define the security-relevant route or operation set once and
enforce audit writability through a structural wrapper or middleware. Add a
test that enumerates the set and proves every member fails closed.

### 4. DENIED: durable unreconciled count in production composition

`app.py:12-14` correctly calls the `AuditRepository` protocol method when a
repository is injected, and it contains no table knowledge. The tests inject
only an in-memory mock whose count is a field at `tests/test_app.py:5-14`.
`create_app()` defaults the repository to `None`; that is also what the
Dockerfile's factory command invokes. In that production path, `/healthz`
returns the plausible-looking count `0` from `app.py:15-18`, not a durable
count, while returning 503.

Required change: wire the concrete durable repository in the application
factory, fail startup or expose an unmistakable unavailable state when it
cannot be constructed, and test against durable storage rather than only a
field-backed mock.

### 5. CONFIRMED: no direct persistence-schema reach-through

The delivery source imports only the `AuditRepository` protocol in
`app.py:7`. Searches for SQL verbs, SQLite names, target table or column names,
and encrypted target file formats found no delivery access. There is no
`TargetRepository` use at all; `routes.py:103` explicitly says saving is not
implemented. The health endpoint reaches audit only through `is_writable()` and
`unreconciled_attempt_count()`.

This confirms the seam is not violated, but target persistence is absent rather
than integrated through its protocol.

### 6. DENIED: `NO_PAYLOAD` serialization

There is no response-envelope serializer in delivery. Searches of
`src/vcf_ops_mcp/app.py` and `src/vcf_ops_mcp/admin/` found no
`ResponseEnvelope`, `NO_PAYLOAD`, or identity-aware MCP tool binding.
`app.py:49-50` merely mounts an empty FastMCP app.

Required change: implement the delivery serialization point and prove that
fields whose value `is NO_PAYLOAD` are omitted before JSON encoding, while a
literal `None` payload remains present.

### 7. DENIED: CI and deploy semantics

The `ai-log-depot` workflow exists at
`.github/workflows/ai-log-depot.yml`, and lines 82-98 poll `/healthz`.
However:

- Lines 69-80 deploy directly to lab infrastructure and never capture the
  prior digest.
- Lines 95-98 call an opaque `rollback` command rather than redeploying the
  captured prior digest.
- Nothing asserts that rollback leaves persistent volumes untouched.
- The deploy uses `ubuntu-latest`, while the constitution pins CI builds to
  self-hosted runners.
- Lint, fixture scanning, fixture freshness, and skills checks at lines 28-41
  are `echo` stubs.
- The workflow was not executed in this review. Spike 002's missing fleet-caddy
  per-slot configuration externally blocks end-to-end verification.

Testable today: workflow text inspection, unit tests, image build, and local
health behavior. Externally blocked: slot deployment, proxy health, and actual
rollback. The blocked integration does not excuse the absent prior-digest and
volume-preservation mechanics in the workflow.

Required change: capture and validate the prior deployed digest before deploy,
redeploy that exact digest after failed health, make volume preservation
explicit, use the pinned runner model, and replace misleading stub steps or
label the workflow honestly as incomplete.

### 8. DENIED: packaging cleanliness and volume declarations

The image built successfully with:

```text
#17 writing image sha256:64ef7c10fdd62f916cce596a65a4e2e2e58dc6d9a8032bd50a41e049900e32c7 done
#17 naming to docker.io/library/vcf-ops-mcp-review-19efb0c done
#17 DONE 1.1s
```

Inspection produced:

```text
User="appuser" Volumes=null Cmd=["uvicorn","vcf_ops_mcp.app:create_app","--host","0.0.0.0","--port","8000","--factory"]
```

The non-root user is correct. `Dockerfile:28-30` creates `/data`, `/keys`, and
`/audit` directories, but it declares no volume mounts, so the required
separate volumes are not established by this packaging.

No real credential value was found. However, the CI file hard-codes the lab
host and service FQDNs at lines 69, 80, 88, and 98. That violates the explicit
requirement that no target FQDN, hostname, or lab configuration be baked into
CI. The production app also bakes in dummy authentication and a fixed session
secret as noted under claim 2. The workflow writes the deploy key to
`deploy_key` and has no explicit cleanup step.

Required change: declare or provide the three distinct mounts in deploy
configuration, move lab hostnames and slot configuration to approved
deployment configuration, remove all production-looking default credentials
and fixed secrets, and guarantee temporary key cleanup.

### 9. DENIED: scope honesty and stubs

The inline login and dashboard responses avoid missing-template 500s, so the
existing routes fail neither on absent templates nor on `base.html`. That is
the narrow confirmed part.

The broader claim is denied:

- `routes.py:41-44` presents dummy literal-password authentication as a working
  login route.
- `app.py:44-46` presents a fixed placeholder session secret in the production
  factory.
- `routes.py:82-104` presents target registration as a POST route but saves
  nothing.
- `app.py:37-52` presents production composition but defaults the durable audit
  repository to absent.
- The auth-source endpoint presents only display strings, with no wire-value
  contract.
- The commit calls `/healthz` functional even though the container entry point
  always uses the no-repository 503 path.
- The commit claims session rotation, but implementation and test rotate only
  a CSRF token.
- Only `base.html` exists, and no route renders it. The physical templates
  remain honestly absent, but the unused Jinja environment makes the template
  surface look started without a working route.

No test in this slice merely constructs an object and asserts only that it is
not `None`. The weak-test concern appears instead as narrow helper tests that
do not prove route-wide security invariants.

The diff also adds 4,101 unrelated lines outside the authorized delivery
surface: 34 historical `.team/markers` files, `agy_phase1.patch`,
`agy_phase3.patch`, `diff.txt`, `log.txt`, and nine `scratch/` proposal or
critique files. These are not authorized by the delivery workplan and must be
removed from the slice. `src/vcf_ops_mcp/contracts.py` was not edited, which
correctly respects codex-worker's sole ownership.

Required change: remove unrelated artifacts and replace operational-looking
stubs with complete wiring or explicit unavailable behavior that cannot be
mistaken for implementation.

### 10. DENIED: request-local identity entry point

There is no session-level MCP identity cache, which avoids the named
misattribution bug. There is also no request-level identity resolution.
`app.py:37-50` constructs and mounts FastMCP without API-key middleware,
`ApiKeyScopeRepository`, `RequestIdentity`, or `extract_request_identity`.
Mounting an empty transport is not the composition required by spike 001 and
`contracts.py`.

Required change: resolve the presented key independently for every HTTP request,
put the resulting `RequestIdentity` on that request's state, bridge the exact
request into the MCP handler context, and add a same-session test that changes
the key header and observes the new identity.

## Baseline checks

### Default suite

The first literal repository invocation could not import the source package:

```text
$ PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider
collected 0 items / 4 errors
E   ModuleNotFoundError: No module named 'vcf_ops_mcp'
=========================== short test summary info ============================
ERROR tests/test_admin.py
ERROR tests/test_app.py
ERROR tests/test_auth.py
ERROR tests/test_contracts.py
!!!!!!!!!!!!!!!!!!! Interrupted: 4 errors during collection !!!!!!!!!!!!!!!!!!!!
============================== 4 errors in 0.55s ===============================
```

Running the default suite in an isolated environment with the declared runtime
dependencies and `src` import path passed:

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --no-project --with 'mcp>=1.2.0' --with jinja2 --with python-multipart --with itsdangerous pytest -p no:cacheprovider
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

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 20 passed, 1 warning in 1.74s =========================
```

### Dash rule

The required command produced one match:

```text
$ git grep -nP '[\x{2014}\x{2013}]' 19efb0cdab604a7a6f38d5e6e512ea99ffa63c2a -- src tests docs
19efb0cdab604a7a6f38d5e6e512ea99ffa63c2a:docs/proposals/2/ballots/critic-r3-skills-ownership-vote.md:8:The load argument for **codex-worker** is real but overstated. Critique 1.7 (as restated in claude-worker’s ballot) says delivery as originally scoped (`app.py`, MCP binding, admin, skills, container, CI, first docker.int deploy) was priced at 4[U+2013]6 days and is actually 8[U+2013]12, and that this is the slice Gate 1 hangs on.
```

That file is not introduced or edited by this slice, so the delivery diff adds
no em dash or en dash under `src`, `tests`, or `docs`. The repository-level
baseline still fails the literal command and should be corrected by its owner.
The two forbidden characters in the command's real output are represented as
`[U+2013]` above so this marker does not introduce new forbidden characters.

### Secrets and lab identifiers

A scan of added lines in `.github`, `Dockerfile`, `pyproject.toml`, `src`, and
`tests` for credentials, tokens, API keys, sessions, lab hostnames, and related
terms found no real secret values. It did find:

```text
.github/workflows/ai-log-depot.yml:59: password: ${{ secrets.GITHUB_TOKEN }}
.github/workflows/ai-log-depot.yml:71: DEPLOY_KEY: ${{ secrets.DOCKER_INT_DEPLOY_KEY }}
.github/workflows/ai-log-depot.yml:80: ssh ... deploy@docker.int.sentania.net ...
.github/workflows/ai-log-depot.yml:88: curl ... https://vcf-ops-mcp.int.sentania.net/healthz
.github/workflows/ai-log-depot.yml:98: ssh ... deploy@docker.int.sentania.net ...
src/vcf_ops_mcp/admin/routes.py:43: if password == "admin":  # Dummy check
src/vcf_ops_mcp/app.py:45: Middleware(SessionMiddleware, secret_key="change_me_in_production_from_env_var")
```

Secret references are normal GitHub Actions indirection, not secret values.
The hard-coded lab identifiers and application placeholders are violations as
described in claims 2 and 8.

### Protected path and synthesis scope

The protected path is authorized by accepted decision 009, signed by all three
doers. The intended implementation files fall within the delivery slice in
`docs/proposals/2/WORKPLAN.md:102-120`. The implementation does not meet that
slice's acceptance criteria, and the unrelated 4,101 artifact lines are
outside its ownership. No delivery edit touches `contracts.py`.

### Diff hygiene

`git diff --check 33bca5d..19efb0c` reports extensive trailing whitespace in
the workflow, source, tests, historical markers, patches, logs, and scratch
files. This is additional cleanup required before re-review.
