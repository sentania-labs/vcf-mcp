# Sentania VCF Ops MCP (unofficial)

`vcf-ops-mcp` is a containerized, read-only-by-default MCP server with a small
admin UI for VCF Operations. The current MVP exposes the implemented inventory,
metrics, alerts, report-definition, target, and skills reads through
authenticated Streamable HTTP. Every MCP tool call passes through the durable
audit dispatcher.

This is an unofficial personal-lab project. It is not a Broadcom or VMware
offering.

## Run the test suite

Python 3.12 or later is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip hatchling
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest tests/
./tools/generate_agents_md.sh --check
./tools/consensus-check.py --self-test
```

The live-appliance tier is skipped unless its explicit guard variables are
provided. Normal tests use only synthetic VCF Ops responses.

## Build and start the container locally

The service creates its session signing secret and credential keyring on the
`/keys` volume at first start. No hand-authored `SESSION_SECRET` is required.

```sh
docker build -t vcf-ops-mcp:local .
docker volume create vcf-ops-mcp-data
docker volume create vcf-ops-mcp-keys
docker volume create vcf-ops-mcp-audit
docker run --name vcf-ops-mcp --rm \
  --read-only \
  --user 10001:10001 \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  -p 8000:8000 \
  -e PUBLIC_BASE_URL=http://localhost:8000 \
  -v vcf-ops-mcp-data:/data \
  -v vcf-ops-mcp-keys:/keys \
  -v vcf-ops-mcp-audit:/audit \
  vcf-ops-mcp:local
```

In another terminal:

```sh
curl --fail http://localhost:8000/healthz
```

A ready response is HTTP 200 and reports all four dependencies as true:
`audit_writable`, `configuration_ready`, `session_secret_persistent`, and
`mcp_ready`. An unavailable audit, configuration, key, or MCP dependency keeps
the process diagnosable but returns HTTP 503.

The production slot uses [deploy/compose.yml](deploy/compose.yml), the external
`docker-slots` network, and the same three persistent volumes. CI supplies only
`images.env`, which pins the image digest. Runtime secrets never pass through
CI or the compose environment.

## First admin sign-in

The approved bootstrap path uses an operator-supplied password file. The
service starts healthy without it, but the admin plane stays inaccessible until
the file exists. The password must contain at least 16 bytes. It is hashed with
scrypt into the runtime database and the bootstrap file is removed when the
first login initializes the account. If that removal fails, a later login
retries the cleanup without changing the stored admin password.

For the local container, create the file without placing the password in shell
history or process arguments:

```sh
docker exec -it vcf-ops-mcp sh
umask 077
python -c 'import getpass,pathlib; pathlib.Path("/keys/admin_bootstrap_password").write_text(getpass.getpass("New admin password: "))'
exit
```

For the docker.int slot, lab-admin performs the same one-time operation through
the host's normal administrative channel inside the running
`vcf-ops-mcp-web` container. The deploy key cannot and must not perform it,
because its forced-command allowlist intentionally excludes `exec`. The file
path and mode are the same. CI never receives the bootstrap password.

Open `http://localhost:8000/admin/login`, sign in as `admin`, then:

1. Register a VCF Ops target. New targets are always `read_only`. The production
   FQDN is recognized server-side and can never be switched to actions in this
   MVP.
2. Select the required implemented read scopes and one or more registered
   targets, then mint an MCP API key. The plaintext key is displayed once.
   Only its SHA-256 digest is stored.
3. Configure the MCP client with Streamable HTTP URL
   `http://localhost:8000/mcp/` and header
   `Authorization: Bearer <displayed-key>`.
4. Use `list_targets` to discover permitted target IDs, then call a read tool.
   VCF adapter arguments are passed in that tool's `arguments` object.
5. Inspect `/admin/audit` to see the append-only attempt and terminal records.

Production uses `https://vcf-ops-mcp.int.sentania.net`, which keeps the admin
session cookie `Secure`. Local HTTP is enabled only when `PUBLIC_BASE_URL`
explicitly uses `http://`.

## Persistent data and recovery

The three volume roots have separate jobs:

| Volume path | Contents |
| --- | --- |
| `/data` | Runtime SQLite database with admin hash, target metadata, encrypted credential envelopes, and API-key digests |
| `/keys` | Generated session secret, audit argument-digest key, versioned AES-256-GCM credential keyring, and the one-use admin bootstrap file |
| `/audit` | Append-only SQLite audit ledger |

Back up `/data`, `/keys`, and `/audit` as separate protected artifacts. Losing
`/keys` while encrypted target records remain is intentionally unrecoverable.
The server refuses to regenerate the credential keyring over existing
ciphertext. Do not use `docker compose down -v` for an established deployment.

If a process dies after committing an audit attempt but before its terminal
record, the next start appends `outcome_unknown`. It never rewrites the attempt
or invents a successful result.

## MVP boundary

Shipped:

- Automatic durable `SESSION_SECRET` generation, with an explicit environment
  override retained for direct process operation.
- Durable encrypted target configuration, bootstrap-admin login, scoped API-key
  mint and revoke, target registration, and audit viewing.
- Authenticated Streamable HTTP with the implemented read adapters, target
  discovery, and both skills tools and skills resources/prompts. Skill content
  over resources and prompts requires the same `read:skills` capability as the
  skills tools; only concrete resource discovery is available without it.
- Read-only target posture, API-key target allowlists, default-deny implemented
  scopes, the production-target hard block, response projection and caps, and
  durable per-tool audit.

Intentionally deferred:

- All action execution, action-capable keys, report runs, plan/apply, and async
  task polling. These remain behind the Phase 2 human gate.
- Target editing and credential rotation in the UI.
- Completed-report download, because the development appliance has no completed
  reports without first running a report mutation.
- External exposure, NSX, VCFA automation, direct-vCenter tools, and PII
  scrubbing.
- Non-LOCAL authentication-source discovery. The earlier arbitrary-FQDN fetch
  was removed because it was an SSRF boundary, not a safe discovery mechanism.

See [docs/SPEC.md](docs/SPEC.md), the accepted records in
[docs/decisions](docs/decisions), and [docs/read-plane.md](docs/read-plane.md)
for the full contract and measured VCF Ops behaviors.
