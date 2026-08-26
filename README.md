# Sentania VCF MCP prototype (unofficial)

`vcf-mcp` is a containerized prototype of the multi-product VCF MCP design.
One process serves separate, flat Streamable HTTP tool surfaces for each
registered product:

- `/ops/mcp` for VCF Operations
- `/vcenter/mcp` for vCenter Server
- `/nsx/mcp` for NSX
- `/sddc-manager/mcp` for SDDC Manager
- `/ops-networks/mcp` for VCF Operations for Networks
- `/fleet-lcm/mcp` for VCF Fleet Lifecycle
- `/sddc-lcm/mcp` for VCF SDDC Lifecycle
- `/log-management/mcp` for VCF Log Management
- `/vsan-dp/mcp` for vSAN Data Protection
- `/vcf/mcp` for read-only management information

The product definitions are data-only backend packs. All nine
built-in product packs publish exactly 19 typed tools, with no compressed or
collapsed tool contracts. Each product endpoint exposes only its own typed
tools. A backend that has no registered target at process start has no endpoint
and contributes no tools.
Every tool call still crosses the mandatory authorization and durable audit
dispatcher.

This is an unofficial personal-lab project. It is not a Broadcom or VMware
offering.

## What the prototype proves

- The admin UI registers every built-in backend target, edits its display
  name, FQDN, credentials, posture, root CA, and per-target TLS policy.
- New targets start with TLS verification disabled. The UI labels that state
  plainly. An operator can upload a PEM root CA and enable verification for
  that target without changing process-wide trust.
- Credential edits use the same AES-256-GCM store as registration. Root CA
  bundles are encrypted through that same keyring-backed path.
- Enabling TLS verification, replacing a CA, or removing a CA cancels requests
  already running through that target. Other edits drain started work and
  discard results from the superseded target generation.
- API keys select endpoints, capabilities, and targets. Revocation applies on
  the next request.
- Local mode supports many explicitly scoped keys and defaults new keys to no
  tool scope. Gateway mode issues one broad key per endpoint registration.
  Switching modes revokes every active key in the same transaction.
- Audit rows identify the endpoint plus the backend pack ID, SHA-256 digest,
  version, authorization mode, and key owner that defined each call.
- Three consecutive authentication failures lock one target before another
  request can reach it. The admin UI shows and clears that persistent state.
- Each backend has bounded concurrency and bounded exponential 429 backoff.
- Every declared tool owns an explicit response-field allowlist. There is no
  backend-wide fallback that can accidentally grant a sensitive field.
- Credential keys rotate online in resumable batches. Startup quarantines one
  integrity-failed target and refuses readiness if every configured target
  fails.
- `/vcf/mcp` exposes wired backends, granted access, health, skills, and call
  history. History is filtered by both the presenting key and
  `X-VCF-Caller-ID`, and returns nothing without that caller header.

Fixture tests make typed calls using Basic authentication, OpsToken, bearer
tokens, SDDC Manager token pairs, VCF Operations token exchange, and vCenter
session IDs. They also prove that an operator pack can load alongside the
official built-in set. Signed-pack tests prove the exact cosign argument
array, workflow identity, issuer pin, OCI manifest and layer validation,
offline startup verification, retention, and rollback. A real scratch
round trip also proves GHCR storage, keyless signing, identity rejection, and
anonymous pull. These tests do not contact a lab appliance.

## Prototype boundary

This is a workable lab prototype, not the finished VCF MCP product. Per-endpoint
token-budget warnings and install refusal remain deferred.

Operator packs are installed from the admin UI, either through public GHCR
version discovery or by uploading a pack and its Sigstore bundle while
disconnected. The container runs digest-pinned cosign and pins verification to
`.github/workflows/release-packs.yml@refs/heads/main` with the GitHub Actions
issuer. Registry artifacts are saved locally with their signature material so
startup verification remains offline. The immutable default trust root is
baked into the image. An operator refresh from the fixed URL is persisted on
`/data` and takes precedence when present. Installation and rollback stage
files for the next restart because the active registry stays frozen. Unsigned install
is off by default, persistently flagged when enabled, and refused whenever any
target permits actions. Fingerprint pinning remains intentionally excluded.
Uploaded CA bundles are the appliance TLS trust mechanism.

The fixture proof cannot establish the following without Scott's hardware:

- compatibility with the real product versions and endpoint base paths in the lab
- the bearer-token source expected by Fleet Lifecycle and SDDC Lifecycle
- Log Management token exchange and Operations for Networks bearer behavior
- successful TLS handshakes against the lab CA chain
- the exact response shapes and permissions of the devel appliances
- Streamable HTTP behavior through the lab reverse proxy
- credential decryption and audit continuity after a real container restart
- a real release bundle verifying offline with the shipped trust root
- gateway reachability isolation or mutual TLS outside the application
- authentication lockout behavior against the DEVEL appliance and its identity source
- real 429 timing and safe concurrency values for each product
- response allowlists against the complete live response shapes
- rotation and separate-artifact restore across the deployed volumes

No lab credentials were requested or used. The operator verification packet is
in [docs/PROTOTYPE.md](docs/PROTOTYPE.md).

## Test locally

Python 3.12 or later is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip hatchling
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest tests/
./tools/generate_agents_md.sh --check
./tools/consensus-check.py --self-test
```

The live-appliance tier remains skipped unless its explicit guard variables are
provided. Normal tests use synthetic appliance responses only.

## Build and start the container

The service generates its session signing secret and credential keyring on the
`/keys` volume at first start. No hand-authored `SESSION_SECRET` is required.

```sh
docker build -t vcf-mcp:prototype .
docker volume create vcf-mcp-data
docker volume create vcf-mcp-keys
docker volume create vcf-mcp-audit
docker run --name vcf-mcp --restart unless-stopped \
  --read-only \
  --user 10001:10001 \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  -p 8000:8000 \
  -e PUBLIC_BASE_URL=http://localhost:8000 \
  -v vcf-mcp-data:/data \
  -v vcf-mcp-keys:/keys \
  -v vcf-mcp-audit:/audit \
  vcf-mcp:prototype
```

The restart policy is required for the console restart action. Without Compose,
Kubernetes, or `--restart unless-stopped`, the orderly restart exits the process
and the appliance stays down until an operator starts it again.

Check readiness with `curl --fail http://localhost:8000/healthz`. A ready
response is HTTP 200 and reports `audit_writable`, `configuration_ready`,
`session_secret_persistent`, and `mcp_ready` as true.

An HTTP 503 response includes `startup_errors` when startup could not load a
required store, key, secret, or catalog. Each entry reports the concrete cause
and affected path so volume ownership and permissions can be distinguished
from database or configuration failures.

## First admin sign-in and backend wiring

Open `http://localhost:8000/admin/login`. The first-run interface requires an
operator-supplied admin password of at least 16 bytes, hashes it immediately
with scrypt, and never retains the source value. There is no default password
and no file-editing prerequisite. The one-use password-file bootstrap remains
available for orchestrated deployments.

1. Register the product targets needed by this appliance. Leave TLS disabled
   only until the correct CA is uploaded.
2. Use **Restart appliance now** in the startup-frozen endpoints notice.
   Backend packs are selected and tool registries are frozen at startup, so the
   first registration for a product needs an orderly process restart. Sessions
   disconnect. The appliance returns automatically only when its container has
   a restart policy, or when it runs under Compose or Kubernetes.
3. Edit each target, upload its CA bundle, enable TLS verification, and save.
4. Choose local or gateway authorization mode. Changing an existing mode
   revokes every active key.
5. Mint local keys with explicit scopes and optional target restrictions, or
   mint one gateway key for each upstream endpoint registration.
6. Configure MCP clients with `Authorization: Bearer <displayed-key>` and the
   endpoint URL. The plaintext key is displayed once.
7. Use `/vcf/mcp` `list_targets` to obtain target IDs, then call a typed tool on
   each product endpoint.
8. Inspect `/admin/audit`, revoke the key, and confirm its next request fails.

## Persistent data and recovery

| Volume path | Contents |
| --- | --- |
| `/data` | Runtime SQLite database with the admin hash, target metadata, encrypted credential and CA envelopes, API-key digests, operator packs, and the persisted refreshed pack trust root |
| `/keys` | Session secret, audit digest key, AES-256-GCM credential keyring, and optional one-use admin bootstrap file |
| `/audit` | Append-only SQLite audit ledger |

Back up `/data`, `/keys`, and `/audit` as separate protected artifacts. The
database backup API refuses to write into the keyring volume, and the recovery
test restores a database artifact with a separately held keyring. Losing
`/keys` while encrypted target records remain is intentionally unrecoverable.
The server refuses to regenerate the credential keyring over existing
ciphertext. Do not use `docker compose down -v` for an established deployment.
Use the admin UI to run credential-key rotation in resumable batches.

See [docs/SPEC.md](docs/SPEC.md), [docs/PROTOTYPE.md](docs/PROTOTYPE.md), and
the accepted [decision records](docs/decisions) for the governing contracts and
measured Operations behavior.
