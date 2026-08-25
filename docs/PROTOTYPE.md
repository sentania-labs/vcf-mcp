# Full governance delivery note

This document is the proposed pull request body and operator verification
packet for the VCF MCP governance delivery. It distinguishes fixture proof
from proof that requires Scott's lab.

## Summary

This change completes four governance areas and applies the captain's live
project rename:

- local and gateway authorization modes, with transactional revocation of
  every active key whenever the mode changes
- signed operator-pack installation with exact GitHub workflow identity and
  issuer pinning, offline Sigstore verification, staged confirmation, retention,
  and rollback
- response allowlisting owned by every tool, a persistent failed-auth lockout,
  and per-backend concurrency plus bounded 429 backoff
- online resumable credential-key rotation, startup row-integrity quarantine,
  unambiguous length-prefixed associated data, and separate database and
  keyring backup handling
- the live package, imports, image, deployment configuration, instructions,
  and product prose renamed to `vcf_mcp` or `vcf-mcp`

The historical records under `docs/decisions`, `docs/artifacts`, and
`docs/history` retain the former project name exactly as written. Rewriting
those records would falsify their contemporary context. The pull request body
reports 124 changed files and 52 historical files containing the former name
that were deliberately left unchanged.

Product endpoints remain frozen for a process lifetime. Signed pack installs
and rollbacks take effect after restart. Startup verifies the active operator
pack before its bytes reach the loader, and the loader requires an explicit
response allowlist on every tool.

## Fixture and artifact evidence

The local tests and built container prove:

- local mode supports separately scoped keys and empty scope denies all tools
- gateway mode has one broad key per endpoint registration
- changing authorization mode revokes every active key in one transaction
- audit records identify mode and configured key owner
- cosign receives the exact workflow identity, GitHub issuer, bundle, trusted
  root, offline flag, and pack bytes
- a signature, digest, identity, or issuer mismatch is refused and audited
- unsigned install is off by default, remains visibly flagged when enabled,
  and cannot coexist with action-enabled targets
- every declared tool owns its own response-field allowlist, including tools
  that return secret-like objects
- three consecutive authentication failures persistently lock one target until
  an operator clears it
- backend concurrency is bounded and repeated 429 responses use bounded,
  exponential backoff with a first-activation warning
- credential rotation resumes from durable progress after interruption and
  retires unused old keys only after completion
- startup quarantines a damaged row while preserving healthy targets, then
  refuses readiness when every configured target fails integrity verification
- a database backup excludes the keyring and restores successfully only when
  paired with the separately retained keyring artifact
- the renamed container builds and its real `/healthz` endpoint reports ready
  while running read-only as the non-root application user

Run the proof with:

```sh
.venv/bin/pytest tests/
ruff check src tests
./tools/generate_agents_md.sh --check
./tools/consensus-check.py --self-test
docker build -t vcf-mcp:local .
```

## Operator verification still required

The following cannot be proven from this worktree because it cannot reach the
captain's appliances and no lab credentials were requested:

### Authorization modes

- gateway reachability isolation, mutual TLS, and gateway-provided caller
  attribution outside the application boundary
- key revocation behavior through the deployed reverse proxy after a live mode
  change

### Pack trust

- a real release bundle from the pinned workflow verifying offline with the
  trusted root shipped in the production image
- signed feed install, restart activation, and rollback on the deployed volumes

### Response safety, authentication lockout, and rate limiting

- response allowlists against the complete response shapes of every lab product
- lockout behavior against the DEVEL appliance and its backing identity source
- real 429 timing and safe concurrency values for each appliance generation

### Store contract

- interrupted rotation and resume across a real container replacement
- startup quarantine using a deliberately damaged copied database
- separate database and keyring artifact restore across the deployed volumes

### Existing appliance integration

- compatibility with the real product versions, endpoint base paths,
  permissions, authentication exchanges, and CA chain
- Streamable HTTP behavior through the lab reverse proxy, including buffering,
  idle timeout, header forwarding, and reconnect behavior

Until this packet is complete, those operational claims remain unproven. The
production appliance remains read-only, and any live action testing still
requires the existing Phase 2 approval.
