# 006: API version drift, public 9.0 contracts with bounded capability probes

- **Status:** accepted
- **Date:** 2026-07-20
- **Assignment:** vcf-ops-mcp round 1, architecture forks 1-6
- **Orchestrator run:** `orchestrator-run-20260720-231633`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker

## Context

Fork 6. The lab appliance runs 9.0.2; the available documentation is 9.0 and
9.1. The assignment hoped the appliance might serve its own Swagger/OpenAPI,
which would have made this fork mostly mechanical.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/round1-architecture` | `85cf71244b042709972e8fce4240b3b916965147` |
| codex-worker | `codex/round1-architecture` | `86b3404056be6f67337294dd47bedb477df6a84b` |
| agy-worker | `agy/round1-architecture` | `68e30bdec4329cdb65af5a278ed3388675ba6046` |

**claude-worker:** pin to the 9.0 offline OpenAPI, probe capabilities at target
registration, record drift in-repo, and a CI drift check. **codex-worker:**
public `/api/*` adapters, a capability probe module storing observed release
and response-shape fingerprints, tolerant parsers that still require
safety-relevant fields, opt-in read-only contract tests. **agy-worker:**
defensive parsing with Pydantic `extra="ignore"` and `Optional` typing for
fields absent on 9.0.2.

## Measured facts, DEVEL 9.0.2

Reported by claude-worker, and decisive for this fork:

| Measurement | Value |
| --- | --- |
| Live Swagger/OpenAPI on the appliance | **not served**; 404 at `/suite-api/docs/swagger.json`, `/v2/api-docs`, `/api-docs`, `/docs/openapi.json` |
| `/api/versions/current` | `releaseName` "VCF Operations 9.0.2.0", `major` 2, `minor` 2 |
| `/suite-api/internal/*` without `X-Ops-API-use-unsupported` | 403 with an **HTML** body, not JSON |
| Bogus token | 401 JSON with `apiErrorCode` 1512 |
| `Authorization` scheme | both `vRealizeOpsToken` and `OpsToken` return 200; `Bearer` returns 401 with an **HTML** body |

Note that product version and API major/minor are distinct: `releaseName` says
9.0.2.0 while `major`/`minor` are 2/2. Version strings alone cannot select
behavior.

## A SPEC question raised and closed

claude-worker expected to find a SPEC error in the `Authorization: OpsToken`
line, because vcf-content-factory's shipping `client.py` sends
`vRealizeOpsToken`. It tested both against DEVEL: both are accepted. Broadcom's
own VCF 9.0 documentation settles which is canonical, and the SPEC is correct
while `client.py` uses the supported legacy alias.

**No SPEC amendment is proposed by this round.** claude-worker recorded having
had this backwards before checking, on the grounds that "the shipping client
must be right" is exactly the assumption a peer could inherit. That is the
correct instinct and the reason it is preserved here.

## Critique (phase 2, adversarial)

**claude-worker on agy-worker (A2 context) and codex-worker on agy-worker (6):**
setting undocumented or absent fields to `Optional` and ignoring extras
prevents crashes but can silently turn missing safety data into permissive
behavior. agy-worker did no live recon, so this fork rested on estimate rather
than evidence.

**codex-worker on claude-worker (7):** registration-time probes plus a manual
reprobe button do not detect an appliance upgrade until some later call happens
to observe a release name, and most domain calls do not return one. Ten targets
make manual reprobe operational debt.

**claude-worker on codex-worker (C2):** acquiring an `OpsToken` requires a
username and password, so putting a DEVEL credential into repo Actions secrets
so a CI job can acquire one **violates the constitution rule "No lab
credentials or secrets ever enter this repo, CI, logs, or transcripts."** The
CI carve-out in Pinned tooling is explicitly for deployment configuration,
"which is not credentials." A decision record cannot weaken an invariant.

**claude-worker on codex-worker (C5):** no response-shaping story. See 001,
where field projection is made a Phase 1 requirement.

## Orchestrator ruling on the CI credential question

claude-worker's constitution-violation claim against codex-worker's fork 6 is
**upheld**, and it is upheld as an invariant rather than settled as a
preference. codex-worker framed live contract tests as needing "a decision plus
an endpoint-specific compatibility test." That is the wrong instrument: a
decision record cannot authorize what the constitution forbids, and the
constitution routes anything weakening an invariant to the principal.

**No DEVEL credential enters CI, in any form, under any gating.** CI runs
fixture-backed tests exclusively. Live contract tests against DEVEL are
operator-run local only. If the team later wants CI-side live testing, that is
an escalation to Scott, not a decision record.

codex-worker did not contest this ruling in its ballot, so no principal
escalation of the claim itself is required.

## Decision (phase 3, synthesis)

**Public `/api/*` is the v1 baseline, pinned to the 9.0 offline OpenAPI as a
compatibility floor.** There is no live schema to introspect, so fork 6 cannot
lean on runtime introspection and is designed accordingly.

**No generated client bound to either OpenAPI file.** Generated clients tend to
reject undocumented fields and cannot represent live omissions reliably, and
recon already proves documented 9.1 paths can 404 on 9.0.2.

**Typed domain adapters, never URLs in tool handlers.** `vcf/client.py` owns
`/suite-api` URL construction, `OpsToken` acquisition, in-memory token storage,
one reauthentication attempt after 401, timeouts, TLS verification, and token
release at shutdown. Authentication errors and logs never include response
bodies.

**Send `OpsToken`**, the canonical 9.x scheme, not the legacy alias.

**Parsers require what safety depends on and tolerate the rest.** This is the
synthesis of agy-worker's tolerance and codex-worker's strictness, and the line
is drawn deliberately: fields used for identity, pagination, authorization,
action targeting, and task outcome are **required**, and a missing one is an
error rather than a `None`. Extras are tolerated only on descriptive payloads.
agy-worker's blanket `Optional` is rejected precisely because a missing
safety-relevant field silently becoming `None` is how a read path turns
permissive.

**Error decoding must not assume JSON.** Measured: `/internal/*` returns HTML
on 403 and a bad `Authorization` scheme returns HTML on 401. A parser that
assumes a JSON error envelope crashes or misreports on exactly the paths where
correct behavior matters most.

**Capability probes on a bounded TTL, failing closed for safety-relevant
capabilities.** codex-worker's point 7 carries over claude-worker's
registration-plus-manual-button model: probe cheaply on a TTL rather than
relying on an operator noticing an upgrade. Store observed release, supported
capabilities, last verification, and response-shape fingerprints. Version
strings alone never select behavior, because product version and API
major/minor differ.

**`/internal/*` is not used in v1.** Any future use lives in a visibly separate
adapter, sends `X-Ops-API-use-unsupported: true`, and requires its own decision
record plus an endpoint-specific compatibility test. No silent fallback from a
public path to an internal one: a wrong fallback can cross from read behavior
into mutation.

**Fixtures are sanitized synthetic contracts, not committed raw recon.**
Sanitization replaces values while preserving types and cardinality, followed
by a secret and hostname scan before commit. No test path knows the prod
hostname. Live contract tests assert an explicit hostname allowlist and reject
every method except GET and the documented token acquire/release POSTs.

## Escalated to the principal

**A DEVEL API service account.** claude-worker reports that no VCF Ops API
credential exists in the lab inventory for this project's own use; its recon
borrowed vcf-content-factory's existing `devel` profile. The build round needs
a credential provisioned for this project, entered post-deployment through the
admin UI per the constitution. This is a provisioning request to Scott, not a
design question.

**Status as of 2026-07-21: in flight.** Scott had lab-admin provision a
read-only `vcf-ops-mcp` account on the devel and prod vROps appliances; the
cross-workspace request is filed. **The account must be confirmed to have landed
before Phase 1 recon depends on it.** Until it does, recon continues to borrow
vcf-content-factory's `devel` profile, which is what this round's recon used.

Note the account is read-only on both appliances, which is consistent with the
constitution's prod hard block: a prod registration can only ever be read-only
until Scott personally flips it, and no action executes against any appliance
before the Phase 2 gate.

## Division of labor

| Piece | Assigned to | Why this harness |
| --- | --- | --- |
| `vcf/client.py`, token lifecycle, 401 reauth, timeouts, TLS, HTML-aware error decoding | agy-worker | Defensive parsing of drifting live JSON is its stated strength and its self-claimed slice, and this is a read-only surface where its weaker safety-model showing this round carries no action risk |
| Read-only domain adapters: inventory, metrics, alerts, report definitions | agy-worker | Same reasoning; it asked for this slice and the work is well matched to it |
| Capability probes, TTL, response-shape fingerprints, required-versus-tolerated field policy | codex-worker | It specified the probe model and the strict/tolerant line, and its critique found where blanket tolerance turns permissive |
| Sanitized fixture capture, hostname allowlist assertions, CI fixture-only enforcement | claude-worker | It did the recon that produced the shapes and it raised the CI credential invariant; the resident that found the boundary enforces it |

## Dissent

**codex-worker's fork 6 lost on the CI contract-test question.** Its position
is recorded verbatim:

> Contract tests against DEVEL would be opt-in and read-only, assert an
> explicit hostname allowlist, reject every method except GET and the token
> acquire/release POSTs, and run outside normal CI unless an approved secret is
> available.

The final clause is what lost. Everything preceding it is adopted.

**agy-worker's blanket `extra="ignore"` plus `Optional` typing lost.** Its
position is recorded verbatim:

> We will rely on Pydantic models configured with `extra="ignore"` to tolerate
> undocumented fields gracefully. [...] Any fields present in the 9.1 docs but
> missing in 9.0.2 will be typed as `Optional`.

agy-worker also lodged a standing objection against codex-worker's probes,
recorded verbatim:

> Codex's reliance on static typing and registration-time probes will remain
> brittle against undocumented live-appliance drift compared to defensive
> parsing.

This objection is partly sustained: it is why the TTL-bounded probe replaced
the registration-time-plus-manual-button model, rather than the probe model
being adopted as codex-worker first wrote it.

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
