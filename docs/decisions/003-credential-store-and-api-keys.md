# 003: credential store encryption and the API-key model

- **Status:** accepted; residual risk **ratified by the principal 2026-07-21** (Option A), with a deferral recorded below
- **Date:** 2026-07-20
- **Assignment:** vcf-ops-mcp round 1, architecture forks 1-6
- **Orchestrator run:** `orchestrator-run-20260720-231633`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker

## Context

Fork 3, which bundles two problems that want different answers. VCF Ops
credentials must be **reversibly** encrypted, because the server replays them
to `POST /api/auth/token/acquire`. MCP API keys must be **irreversibly**
hashed, because the server only ever needs to verify them.

CLAUDE.md "Pinned tooling" names the credential-store encryption design a
round-1 architecture decision to be recorded before code depends on it.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/round1-architecture` | `85cf71244b042709972e8fce4240b3b916965147` |
| codex-worker | `codex/round1-architecture` | `86b3404056be6f67337294dd47bedb477df6a84b` |
| agy-worker | `agy/round1-architecture` | `68e30bdec4329cdb65af5a278ed3388675ba6046` |

**claude-worker:** AES-256-GCM with a rotatable keyring file, AAD binding each
ciphertext to `target_id|field_name|key_id`; HMAC-SHA256 over high-entropy
random API keys rather than Argon2, on the grounds that a 256-bit random token
does not need a memory-hard KDF. **codex-worker:** a versioned JSON keyring on
the secrets volume at mode 0600, `AESGCM` with a fresh 96-bit nonce per record,
AAD binding to schema version, target ID, field purpose, and key ID; opaque
`vok_<public-id>_<secret>` keys stored as SHA-256 digests with a scope enum and
optional target allowlist; an online resumable rotation state machine.
**agy-worker:** SQLite plus a 256-bit key file, "AES-GCM (via the
`cryptography` library's Fernet or raw AESGCM)", SHA-256 hashed API keys.

## Critique (phase 2, adversarial)

**claude-worker on agy-worker (A3):** "Fernet or raw AESGCM" is not a design
choice. Fernet is AES-128-CBC with HMAC-SHA256, not AES-GCM. They differ in
key size, in whether associated data can bind ciphertext to a row (Fernet
cannot), and in rotation model. A credential-store fork that cannot name its
own primitive is not ready to be a decision record.

**codex-worker on agy-worker (3):** the key model omits target allowlists and
the unconditional prod action block, and codex named this a constitution
violation in exactly those terms: "**the prod appliance is hard-blocked from
actions**" and "**read-only is the default posture, per target**."

**claude-worker on codex-worker (C3):** the keyring sits next to the ciphertext
it protects. For a single container with the SQLite database and the keyring
both on mounted volumes, whoever can read the `.db` can read the `.json` beside
it. "Database-only theft" is a threat that barely exists in that arrangement,
yet the fork still presents encryption at rest as the load-bearing control.

**codex-worker on claude-worker (4):** a 60-second positive key cache
contradicts the claim that revocation is immediate and creates a real
post-revocation action window. **agy-worker agreed**: "A 60-second window where
a revoked key can still execute a destructive infrastructure action is
unacceptable."

**agy-worker on codex-worker:** the escalation of `cryptography` as a new
dependency rests on a false premise, since it is already transitive via the
`mcp` package.

## Orchestrator ruling on the dependency dispute

agy-worker and claude-worker are right on the **fact** and codex-worker is
wrong: a clean venv with `mcp==1.28.1` installs `cryptography` 49.0.0
transitively via PyJWT. It is not a new dependency.

codex-worker is nonetheless right on the **governance**, for a reason it did
not state precisely. CLAUDE.md "Pinned tooling" makes the credential-store
encryption design a round-1 architecture decision requiring a record before
code depends on it, and that obligation is independent of whether the library
is new. This record discharges it. agy-worker's characterization of the
escalation as something that "wastes the orchestrator's time" is rejected:
the conclusion was right even though the premise was wrong.

## Decision (phase 3, synthesis)

### Target credentials

**AES-256-GCM via `cryptography`'s `AESGCM`, fresh 96-bit nonce per record.**
Fernet is rejected on claude-worker's A3 reasoning: no AAD support, and AAD is
the specific feature wanted.

**AAD binds each ciphertext to its row.** codex-worker's four-part binding
(schema version, target ID, field purpose, key ID) carries over claude-worker's
three-part binding, because schema version makes envelope migration
expressible. claude-worker conceded this outright: "more specific than my
envelope design and is strictly better. Adopt it."

The property this buys is worth stating plainly, because it is the reason the
constitution's prod hard-block gets a second layer: a ciphertext lifted from
the prod target's row and pasted into the devel target's row fails to decrypt
rather than silently working.

**A versioned keyring**, not a single unversioned key file, so rotation is not
an outage-prone all-or-nothing rewrite. Rotation is online and resumable: add
a new active key, keep old keys decrypt-only, re-encrypt in bounded
transactions with progress in a rotation table, verify every row, retire.
Removal is a separate step, refused while any row references the key.

**Fail closed at startup** if ownership or permissions are unsafe, if the
keyring is absent while ciphertext exists, or if decryption integrity fails.
Never regenerate a missing keyring over existing ciphertext.

**Losing the keyring is intentionally unrecoverable**, so backup and restore is
a Gate 1 test, not a runbook paragraph.

### Keyring co-location, ballot 2

Voted **4-0 for Option A**: accept volume co-location for v1, with the threat
model stated honestly and separation enforced.

The record is not acceptable without saying what encryption at rest actually
buys here, in claude-worker's words: it closes "a database file copied without
its filesystem context (a backup blob, a volume snapshot mounted elsewhere, an
errant `docker cp` of the data volume). It does not defend against an attacker
with read access to the container filesystem or the host."

Separation is enforced by three implemented controls, and claude-worker's
condition is adopted as binding: if these are not implemented, the encryption
claim is struck from the record rather than softened.

1. A distinct mount for the keyring, not the database volume.
2. Distinct ownership and mode, checked at startup with a fail-closed refusal.
3. Explicit exclusion of the keyring volume from the same backup artifact as
   the database.

**Option B (passphrase-derived KEK at container start) was rejected** on
claude-worker's operational argument, which no one contested: an unattended lab
appliance behind fleet-caddy must survive a host reboot, a daemon restart, and
an image redeploy with no human present. B means each of those ends in a
container that is up, healthy to the orchestrator, and serving nothing. The
predictable operator response is to put the passphrase in an env var in the
compose file on the same host, "which restores exactly the co-location we were
trying to escape while adding a boot dependency and the process-environment
exposure class." A control that degrades into the thing it replaced, plus a new
outage mode, is worse than the honest version of A.

### MCP API keys

**256-bit random opaque tokens**, displayed once, formatted
`vok_<public-id>_<secret>`. Lookup by public ID, then constant-time comparison
of the stored digest. Stored: public ID, digest, label, creation/revocation/use
timestamps, scope enum (`read` or `actions`), optional target allowlist.

**No positive cache.** claude-worker's 60-second cache loses 2-1 in critique
and claude-worker did not defend it in ballots. Revocation takes effect on the
next request, with no bearer-token cache beyond a single request.

**Scope never overrides target posture.** An action requires all of: an
actions-capable key, target allowlist membership if configured, target actions
enabled, a non-prod target, a valid one-use plan, and action-class policy
approval. Any one failing is a refusal. The prod hard-block and the read-only
default are enforced server-side independently of client scope, which is what
agy-worker's model omitted.

## Escalated to the principal, and resolved

Both escalations were resolved by Scott on 2026-07-21.

### 1. Ratification of the residual risk in ballot 2

**As escalated.** codex-worker and agy-worker both voted A while holding that
Scott must accept the residual risk rather than the team accepting it for him.
codex-worker: "The team can recommend the tradeoff, but should not accept its
residual risk for him." claude-worker dissented on the routing (see Dissent) but
agreed Scott sees the threat model when approving this record. The team's
recommendation is Option A with the three enforced controls. Scott ratifies or
overrules.

**Ruling: Option A ratified.** The AES-256-GCM versioned key file stays
co-located with the ciphertext store on the 0600 volume, with the team's three
separation controls (AAD binding, rotatable versioned key, SHA-256-hashed API
keys). Scott accepts the residual risk for MVP, softened by two facts already in
this record: the VCF Ops credentials are read-only, and API keys are stored only
as digests.

### The deferral, and why the obvious fix is not the fix

This is recorded carefully because the intuitive next step is wrong, and a later
reader reaching for it would spend effort buying nothing.

**Runtime key injection does not remove the key from the host. It only
relocates it.** A key injected at runtime is still resident on the same host,
readable by the same root. It is not a separation control; it is the appearance
of one.

The genuine win of separation is getting the key **off the same volume as the
ciphertext**, so that a volume snapshot, a backup, or a self-mount read does not
capture both halves in one grab. That is a real threat and it is the one
claude-worker's C3 critique named. Injection does not achieve it.

**Full host-root compromise is unbeatable at this layer regardless**, whatever
the key transport. Any design claiming otherwise is claiming something it cannot
deliver.

**The correct long-term resolution is an external secrets broker or KMS**, which
is the direction of Scott's parked Vaultwarden/OpenBao work and the framework's
future clerk broker. That, not injection, is what actually moves the key off the
volume and out of the blast radius of a snapshot.

**Action:** a deferral ticket is filed pointing at the broker/KMS direction. It
does not point at runtime key injection, deliberately.

### 2. Whether actions-scoped keys may be minted before the Phase 2 gate

**Resolved, and generalized past the question asked.** See record 001's
"Escalated to the principal, and resolved" for the full ruling. In short: a
scope is assignable only if the server actually implements the matching
capability, read or write, so the grantable-scope set is derived from what is
implemented and there are no phantom grants. Action scopes are not grantable
until the action machinery ships and clears the Phase 2 gate.

This bears directly on the API-key model in this record: the mint path does not
offer a scope the server cannot honour. Record 007 makes the derivation
structural, with the grantable-scope registry built at server start from the
adapters actually registered and enumerated by the admin UI from that registry.

## Division of labor

| Piece | Assigned to | Why this harness |
| --- | --- | --- |
| Versioned keyring, AES-GCM envelope, AAD binding, startup fail-closed checks | codex-worker | It designed the four-part AAD binding and the rotation state machine, and claude-worker conceded its envelope is better |
| Rotation state machine, backup/restore drill, crash tests | codex-worker | Same piece; splitting rotation from the envelope would split one invariant across two residents |
| API-key mint/verify/revoke, constant-time comparison, scope enforcement | claude-worker | It drew the reversible/irreversible distinction the fork framing bundled, and argued the HMAC-versus-KDF point correctly |
| Prod hard-block and read-only posture enforcement tests | claude-worker | It found the missing enforcement in agy's proposal; the resident that spotted the gap writes the test that keeps it closed |

## Dissent

**claude-worker dissents on the routing of ballot 2, not its outcome**, quoted
verbatim:

> Why this is not Scott's. The constitution routes to the principal anything
> that "widens the action blast radius or weakens an invariant." A does neither.
> There is no invariant requiring key/ciphertext separation, and the credential
> store is already an escalated round-1 decision record under Pinned tooling
> per the orchestrator's ruling 1. Scott sees this threat model when he
> approves that record, which is the right place for him to overrule it if the
> lab warrants more. Escalating it separately asks him the same question twice.

**agy-worker dissents in the opposite direction**, quoted verbatim:

> However, Option A effectively reduces "encryption at rest" to mere
> obfuscation against DB-only dumps. Because this choice fundamentally weakens
> the credential security invariant, it is an architecture escalation that
> belongs to Scott, not the team.

The orchestrator resolves these against each other rather than splitting them:
the escalation is folded into the ratification of this record, not raised as a
separate question. That satisfies claude-worker's objection to asking Scott the
same question twice, and satisfies codex-worker's and agy-worker's objection to
the team accepting residual risk on Scott's behalf.

**Constitution-violation claim, resolved.** codex-worker's claim that
agy-worker's fork 3 violated "the prod appliance is hard-blocked from actions"
and "read-only is the default posture, per target" was upheld, and the
synthesized decision enforces both independently of client scope. agy-worker
did not contest it. No escalation is required for an upheld claim against a
losing proposal.

## Protected paths touched

src/vcf_ops_mcp/

## Sign-offs

    Signed-off-by: claude-worker <claude@team.local> 2026-07-20T23:38:12Z
    Signed-off-by: codex-worker <codex@team.local> 2026-07-20T23:33:21Z
    Signed-off-by: agy-worker <agy@team.local> 2026-07-20T23:34:00Z

Transcribed by the orchestrator from each worker's own signature artifact,
because the records live on a branch the workers do not write to. The
artifacts are authoritative and independently checkable:

| Signer | Signature artifact | Commit |
| --- | --- | --- |
| claude-worker | `.team/signoffs/claude-worker-round1-records.md` | `4cde29b` |
| codex-worker | `.team/signoffs/codex-worker-round1-records.md` | `dd9cf51` |
| agy-worker | `.team/signoffs/agy-worker-round1-records.md` | `9576887` |

Each signer confirmed in its artifact that its own dissent, where it has one,
is quoted accurately and was not softened or truncated.
