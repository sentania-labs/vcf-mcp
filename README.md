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

The product definitions are unsigned, data-only backend packs. All nine
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
- Audit rows identify the endpoint plus the backend pack ID, SHA-256 digest,
  and version that defined each call.
- `/vcf/mcp` exposes wired backends, granted access, health, skills, and call
  history. History is filtered by both the presenting key and
  `X-VCF-Caller-ID`, and returns nothing without that caller header.

Fixture tests make typed calls using Basic authentication, OpsToken, bearer
tokens, SDDC Manager token pairs, VCF Operations token exchange, and vCenter
session IDs. They also prove that an operator pack can load alongside the
official built-in set. They do not contact a lab appliance.

## Prototype boundary

This is a workable lab prototype, not the finished VCF MCP product. The
following production work is deliberately deferred:

- cosign signing, identity pinning, the pack trust root, and trust-root refresh
- backend pack feed installation and rollback
- gateway mode and the authorization-mode toggle
- the failed-auth circuit breaker
- upstream rate limiting and backoff
- response redaction
- token-budget warnings and install refusal

The built-in packs load from disk and are unsigned-only. The validated loader
also accepts operator-supplied pack definitions alongside the official set,
without allowing them to replace a built-in product. The server refuses to
put any target into an actions-enabled posture while unsigned packs are in use.
Fingerprint pinning is intentionally not implemented. Uploaded CA bundles are
the trust mechanism.

The fixture proof cannot establish the following without Scott's hardware:

- compatibility with the real product versions and endpoint base paths in the lab
- the bearer-token source expected by Fleet Lifecycle and SDDC Lifecycle
- Log Management token exchange and Operations for Networks bearer behavior
- successful TLS handshakes against the lab CA chain
- the exact response shapes and permissions of the devel appliances
- Streamable HTTP behavior through the lab reverse proxy
- credential decryption and audit continuity after a real container restart

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
docker run --name vcf-mcp --rm \
  --read-only \
  --user 10001:10001 \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  -p 8000:8000 \
  -e PUBLIC_BASE_URL=http://localhost:8000 \
  -v vcf-mcp-data:/data \
  -v vcf-mcp-keys:/keys \
  -v vcf-mcp-audit:/audit \
  vcf-mcp:prototype
```

Check readiness with `curl --fail http://localhost:8000/healthz`. A ready
response is HTTP 200 and reports `audit_writable`, `configuration_ready`,
`session_secret_persistent`, and `mcp_ready` as true.

## First admin sign-in and backend wiring

The approved bootstrap path uses an operator-supplied password file. The
password must contain at least 16 bytes. It is hashed with scrypt and the file
is removed when the first login initializes the account.

For a local container, create it without placing the password in shell history
or process arguments:

```sh
docker exec -it vcf-mcp sh
umask 077
python -c 'import getpass,pathlib; pathlib.Path("/keys/admin_bootstrap_password").write_text(getpass.getpass("New admin password: "))'
exit
```

Open `http://localhost:8000/admin/login` and sign in as `admin`.

1. Register the product targets needed by this appliance. Leave TLS disabled
   only until the correct CA is uploaded.
2. Restart the container. Backend packs are selected and tool registries are
   frozen at startup, so the first registration for a product needs a restart.
3. Edit each target, upload its CA bundle, enable TLS verification, and save.
4. Mint a key with the required product endpoints plus `/vcf/mcp`, explicit
   read capabilities, and matching targets.
5. Configure MCP clients with `Authorization: Bearer <displayed-key>` and the
   endpoint URL. The plaintext key is displayed once.
6. Use `/vcf/mcp` `list_targets` to obtain target IDs, then call a typed tool on
   each product endpoint.
7. Inspect `/admin/audit`, revoke the key, and confirm its next request fails.

## Persistent data and recovery

| Volume path | Contents |
| --- | --- |
| `/data` | Runtime SQLite database with the admin hash, target metadata, encrypted credential and CA envelopes, and API-key digests |
| `/keys` | Session secret, audit digest key, AES-256-GCM credential keyring, and one-use admin bootstrap file |
| `/audit` | Append-only SQLite audit ledger |

Back up `/data`, `/keys`, and `/audit` as separate protected artifacts. Losing
`/keys` while encrypted target records remain is intentionally unrecoverable.
The server refuses to regenerate the credential keyring over existing
ciphertext. Do not use `docker compose down -v` for an established deployment.

See [docs/SPEC.md](docs/SPEC.md), [docs/PROTOTYPE.md](docs/PROTOTYPE.md), and
the accepted [decision records](docs/decisions) for the governing contracts and
measured Operations behavior.
