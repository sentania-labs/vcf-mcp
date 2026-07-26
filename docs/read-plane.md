# The VCF read plane

Implementation notes for `src/vcf_ops_mcp/vcf/`, owned by claude-worker per
record 009 decision 6-sub. Authority is
`docs/decisions/009-phase1-build-synthesis.md` and `docs/proposals/2/SPEC.md`.

This document carries three things the Gate 1 packet needs: the numeric caps
and how they were derived, the measured appliance behaviors that overruled
plausible design, and the open questions this slice cannot answer on its own.

## Layout

| Module | What it owns |
| --- | --- |
| `errors.py` | The typed error hierarchy. Every class carries a stable `error_code`, an `audit_status`, and a `retryable` flag. |
| `outbound.py` | The frozen `(method, path template, permitted query parameters)` allowlist, plus the body-key allowlist this API forces. |
| `client.py` | One client per target: token single-flight, the per-request retry counter, TLS policy, timeouts, and the client registry that implements `TargetClientInvalidator`. |
| `caps.py` | Every numeric cap and its derivation. |
| `projection.py` | What a caller sees. Links dropped, endpoint names never exposed. |
| `adapters/` | The nineteen Phase 1 read tools, each declaring its full outbound contract and projection version. |
| `fixtures/` | The whitelist-based synthetic fixture generator and its declared schemas. |

Tests: `tests/test_vcf_client.py` (tier 2 client contract),
`tests/test_vcf_adapters.py` (tier 2 adapters, allowlist, caps),
`tests/test_vcf_fixture_generator.py` (tier 1), `tests/test_live_guard.py`
(tier 1, guards the live tier), and `tests/live/` (tier 3, opt-in).

Run tiers 1 and 2 with `PYTHONPATH=src python3 -m pytest tests`. Run tier 3
with the command in `tests/live/conftest.py`'s docstring.

## Measured facts that overruled plausible reasoning

Measured against `vcf-lab-operations-devel.int.sentania.net` on 2026-07-25 with
the read-only service account. Nothing was measured against PROD and nothing
was mutated.

1. **`maxSamples` is ignored by `POST /api/resources/stats/query`.**
   `maxSamples: 1` and `maxSamples: 10` return byte-identical 7,485 byte
   responses containing 286 samples. Sample count follows `begin`, `end`, and
   the interval, and nothing else. So `maxSamples` is not a permitted body key:
   sending it would let a caller believe it had bounded a response it had not.
   The ranged-stats adapter requires an explicit window and computes the cap
   from it. This also explains SPEC section 2's "137,808 bytes for one resource
   at `maxSamples=1`" measurement, which was a full-key read over a default
   window rather than a one-sample read.

2. **Alert filtering is asymmetric between the GET and POST forms.**
   `GET /api/alerts?activeOnly=true`, `?alertCriticality=CRITICAL`, and
   `?status=ACTIVE` are silently ignored: 1216 of 1216 every time. The same
   filters in the body of `POST /api/alerts/query` work: `activeOnly` gives 40,
   `alertCriticality: ["CRITICAL"]` gives 703, `["WARNING"]` gives 187, and
   `alertDefinitionId` gives 0 for an id no alert references. `resourceId` is
   the reverse: it filters on the GET form (15) and is ignored in the POST body
   (1216). So the read plane ships two alert-search tools, each declaring only
   the parameters its own endpoint honors.

3. **There is no live symptom detail endpoint.** `GET /api/symptoms/{id}` is a
   404, `GET /api/symptoms?id=` is silently ignored, and every body filter
   tried against `POST /api/symptoms/query` (`id`, `resourceId`,
   `symptomDefinitionIds`, `activeOnly`) returned the unfiltered 879. The only
   effective filter is `GET /api/symptoms?resourceId=`. Symptom detail is
   therefore served as the symptom definition, which does have a working detail
   endpoint at `GET /api/symptomdefinitions/{id}`. No adapter pretends to a
   lookup this API cannot do.

4. **`authSource` for a local user is `LOCAL`**, or omitted entirely. The
   string `Local Users`, which is what the UI calls that source, is a 401. The
   admin picker's "Local users" entry must therefore send `LOCAL`. This matters
   because a wrong auth source and a wrong password are byte-identical 401s, so
   a picker that sends its own label produces the single most confusing failure
   this API can produce.

5. **The unfiltered collection hazard is real and large.**
   `GET /api/resources?identifier=<uuid>` returns all 517 resources in
   1,115,211 bytes with a 200, correctly shaped and correctly paginated, at
   entirely the wrong scope. That is one typo away from a real call.

Facts 1, 2, 3, and 5 are asserted by the live tier on every run, so appliance
drift surfaces as a test failure rather than as a wrong answer.

## The caps, and how the numbers were derived

Amendment 2 ruling 1 assigns the numeric metrics cap to this slice. Full
derivation is in the `caps.py` docstring; the summary for the packet:

A cell is one (resource, stat key, sample) triple. Measured payload for
`stats/query` at a 5-minute rollup: 12 samples of one series cost 535 bytes,
286 samples cost 7,485 bytes, and 5 resources by 20 keys by 286 samples cost
603,732 bytes. So a cell costs 20 to 26 bytes upstream and roughly 6 tokens
once projected to timestamp and value pairs. Record 001 measured a 274,000
token blowup as the thing to prevent. A ceiling of about 30,000 tokens per
metrics call gives 30,000 / 6, so:

| Cap | Value | Posture |
| --- | --- | --- |
| `METRICS_CELL_CAP` | 5,000 cells | Refuse |
| `MAX_METRICS_RESOURCES` | 50 | Refuse |
| `MAX_METRICS_STAT_KEYS` | 25 | Refuse |
| `MAX_METRICS_SAMPLES_PER_SERIES` | 1,000 | Refuse |
| `MAX_UPSTREAM_RESPONSE_BYTES` | 8 MiB | Refuse |
| `MAX_PAGE_SIZE` | 200 | Clamp |
| `DEFAULT_PAGE_SIZE` | 50 | Clamp |

Metrics refuse and lists clamp, on purpose. Paging is lossless and resumable,
so clamping a page size loses nothing. A truncated metric series is
indistinguishable from a quiet period in the data, so a caller cannot tell it
is reasoning about a fragment. Every refusal names the cap and both numbers.

Both stats adapters require an explicit non-empty stat-key list. One resource
with no key filter returned 24,967 bytes across 237 keys, and the key count for
a resource is not knowable before the call, which is what
`discover_stat_keys` exists to answer.

**If capping proves unusable in practice**, response shaping for `stats/query`
is a new slice that appears in nobody's estimate today. That is the risk
register's entry for this slice and it is unchanged.

## Target edit: drain or cancel

The client half of `contracts.py`'s target-configuration-generation protocol.
On an admin edit, after `TargetRepository.save` and before reporting success,
the admin flow awaits `TargetClientRegistry.invalidate`.

- The client for the previous generation is marked closed synchronously, so it
  accepts no new work from that instant.
- `DRAIN` lets already-started requests finish their transfer, then refuses
  their results with `TargetConfigurationSuperseded`, which is retryable. That
  refusal is `contracts.py`'s stated obligation: a generation mismatch discards
  the old result and never retries through the closed client. What DRAIN buys
  over CANCEL is an orderly unwind and a typed retryable error rather than a
  `CancelledError`, and a transport closed with nothing mid-flight on it.
- `CANCEL` cancels those requests where they stand. It is what
  `contracts.invalidation_mode_for_change` selects when an edit tightens TLS
  verification, because continuing a transfer over an unverified connection
  after the operator turned verification on is precisely the thing the operator
  just took away.
- Either way the closed client is removed and its transport closed, and a later
  lookup lazily creates a client only for the new generation.

A caller that receives `TargetConfigurationSuperseded` re-reads the target and
re-issues. It never receives a body fetched with credentials or a TLS policy
the operator has replaced.

## TLS

Per-target configuration on that target's own client, never a process-global
disable. DEVEL presents a self-signed certificate that does not validate
against the host trust store, so the honest first registration is per-target
verification disabled, and the live tier runs that way.

That exposes credentials and tokens to a local network attacker. **The clean
answer is a mounted lab CA bundle, and it is the principal's call** because it
is deployment trust material. Carried as Gate 1 packet item 6 and TLDR issue 4.
Fingerprint pinning is not budgeted and is not built: normal validation cannot
complete a handshake against an untrusted self-signed chain and then perform a
post-handshake fingerprint check, so a correct implementation is a
purpose-built transport plus an explicit first-trust ceremony.

## Open questions this slice cannot answer

1. **The lab CA bundle**, above. Principal's call.
2. **Completed-report listing and download.** This spec ships report definition
   listing and detail only, per SPEC section 6. `GET /api/reports` on DEVEL is
   `totalCount: 0`, re-verified 2026-07-25, and creating a report instance is a
   mutation nobody is authorized to perform in Phase 1. This is a reduction
   against SPEC 4.1's `reports: list/run/download` line and it is flagged to the
   principal rather than taken as a team decision.
3. **Whether the metrics cap is usable in practice.** It is derived from
   payload measurement, not from watching an operator work. Gate 1 is the first
   time anyone reads real metrics through this server.
