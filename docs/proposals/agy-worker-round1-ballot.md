# Round 1 Ballots (agy-worker)

## Ballot 1: Skills content model (fork 5)
**Vote:** Option A
**Interest:** I am a party (proposed Option B).
**Reasoning:** I concede Option B's hot-reload introduces a prompt-injection vector via the volume. While this repo audits every tool call, the audit log only captures the request, not the potentially mutating skill content returned; without versioned, immutable skills, the audit trail cannot definitively reconstruct what instructions the client received. Forcing skills through the repository and CI (Option A) provides verifiable provenance and eliminates the runtime tamper vector, which is worth the iteration friction.

## Ballot 2: Credential keyring co-location (fork 3)
**Vote:** Option A, but escalate to Scott.
**Interest:** None.
**Reasoning:** For an unattended lab appliance behind fleet-caddy, requiring an operator to supply a passphrase on every container restart (Option B) creates an unacceptable availability cost. However, Option A effectively reduces "encryption at rest" to mere obfuscation against DB-only dumps. Because this choice fundamentally weakens the credential security invariant, it is an architecture escalation that belongs to Scott, not the team.

Co-authored-by: Antigravity <agy@team.local>
