# 020: distribute backend packs as signed OCI artifacts

- **Status:** accepted by principal directive
- **Date:** 2026-08-25
- **Assignment:** Move backend-pack updates from a rolling GitHub release feed
  into signed GHCR artifacts, preserve offline and rollback behavior, and add
  a console action for the startup activation boundary.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** principal directive, 2026-08-25: prove GHCR's signed
  non-image OCI round trip first, then make the registry the pack update path,
  retain the v0.3.0 legacy feed transition, preserve all pack trust controls,
  and provide a protected, audited, orderly process restart without Docker or
  cluster credentials.

## Context

The v0.2.0 appliance discovers pack updates through a hand-built `feed.json`
on the rolling `backend-packs` GitHub release. Each pack and its
`*.sigstore.json` blob-signature bundle are separate release assets. That
catalog is another source of truth and does not provide registry-native
version discovery.

Pack routes are intentionally frozen at process startup. Installing a pack or
registering the first target for a product therefore needs a process restart,
but the console previously sent the operator to a terminal for that step.

This is a directive-authority record. The principal selected GHCR, keyless
Sigstore identity pinning, the retained trust and rollback behavior, and the
restart security boundary. No proposal round was authorized or needed.

## Proof before adoption

GitHub Actions run
[`32886757594`](https://github.com/sentania-labs/vcf-mcp/actions/runs/32886757594)
proved the required round trip from the real publishing workflow before the
appliance implementation began:

- GHCR accepted a non-image artifact with type
  `application/vnd.sentania.vcf-mcp.backend-pack.v1+json` at scratch tag
  `pack-proof-32886757594-1`.
- The immutable manifest digest was
  `sha256:1f12b6fb82ca08079b8cf771220f6cdd214609efe0714e2d032eb4456f8f4206`.
- Cosign verified the certificate identity
  `https://github.com/sentania-labs/vcf-mcp/.github/workflows/release-packs.yml@refs/heads/fm/vcf-mcp-registry-packs-and-restart`
  and issuer `https://token.actions.githubusercontent.com`. The same command
  with a deliberately wrong identity failed.
- A separate GitHub-hosted job with no package permission or registry login
  pulled the artifact. Its pack bytes matched source SHA-256
  `bf23fae2ba2a8cf53da4f5a3cf45633e649955261773d698711a86fe8f7a6f28`.

## Decision

Publish versioned pack artifacts into the existing public appliance package:

    ghcr.io/sentania-labs/vcf-mcp:pack-<backend>-<version>

This intentionally adjusts the suggested nested repository layout. GHCR
treats each nested repository as a separate package whose initial visibility
is private. Using the already-public appliance package keeps anonymous pull
behavior under the release gate that already proves it, and avoids nine new
visibility settings that could drift independently.

The publisher pushes one JSON layer with a pack-specific OCI media type,
resolves the immutable manifest digest, and signs that digest through the
unchanged `release-packs.yml` workflow. Existing version tags are immutable:
a rerun accepts a matching, correctly signed artifact and refuses changed
bytes under the same version. A credential-free job then pulls and verifies
every published pack with the exact main-branch workflow identity and GitHub
OIDC issuer.

The appliance asks GHCR for tags, maps product-specific tag prefixes to pack
versions, validates each OCI manifest and layer digest, and shows the
validated version, tool count, and estimated definition tokens before the
operator selects an update. Installation saves the OCI artifact and its
cosign signature as a local OCI layout archive. Confirmation, rollback, and
startup each verify that local archive with the shipped trust root before
parsing the pack, so a registry outage does not weaken startup verification.
Manual pack plus Sigstore bundle upload remains the disconnected update path.

The v0.3.0 pack publication is the last one that also writes the legacy
`backend-packs` release feed for already-running v0.2.0 appliances. Later
project versions skip that compatibility publication. All nine official packs
remain baked into the image and the registry remains an update path only.

## Activation boundary

The console records `operator_restart_requested` in the durable configuration
audit before returning the restart response. After the response is delivered,
the application asks its Uvicorn server to exit. Uvicorn stops accepting new
work, drains in-flight requests for at most ten seconds, runs application
shutdown, and exits with status 0. Compose or a Kubernetes Deployment then restarts the
container. No Docker socket, orchestration API, or cluster credential enters
the appliance.

## Dissent

None. The implementation follows a direct principal instruction.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this change, so it
carries no worker sign-off lines. The `Authority` field above stands in their
place.
