# 013: The audit repository is an append-only SQLite ledger on the /audit volume

- **Status:** accepted
- **Date:** 2026-07-29
- **Assignment:** issue #8, first light: build-deploy green end to end including
  the health gate, and `healthz` 200 through
  `https://vcf-ops-mcp.int.sentania.net/healthz`, with no weakening of the
  health gate or the audit invariant.
- **Orchestrator run:** none. Direct dispatch, no round.
- **Lane:** directive authority
- **Workers dispatched:** None (directive authority)
- **Authority:** principal directive, 2026-07-29: Scott authorized a direct
  dispatch bypassing the wedged round-5 orchestrator on issue #8
  (foundry-ops#24); this record documents the AuditRepository design chosen
  under that authority.

This record is a directive-authority record, and the category is legitimate
here for a specific reason rather than as a convenience. The round-5
orchestrator wedged three times on this exact issue and produced three
triage-only proposal branches with no code. Requiring worker sign-off on this
synthesis would mean waiting on the same mechanism that failed three times to
ratify a decision no worker was ever able to bring to a vote. The principal
directed the change outright instead, and this record stands in for the round
that did not happen. The three unapproved proposals are read as input below
and credited, but they carry no authority and none of them was accepted as
written.

## Context

`/healthz` at the public hostname answered 503 with an empty body. Round 4
(PR #6) already proved the deploy path itself: GHCR push, the slot key, the
private pull, the container-host compose contract, read-only root, and
`docker compose ps` reporting Up. The 503 was the application.

Three independent defects each produced that 503 on their own.

1. **The container could not start.** `deploy/compose.yml` set no
   `SESSION_SECRET`, and `create_app` raises `RuntimeError` without it. The
   entry point was `uvicorn vcf_ops_mcp.app:create_app --factory`, so the
   factory raised at startup, uvicorn exited, `restart: unless-stopped` turned
   that into a crash loop, nothing bound 8000, and fleet-caddy answered 503
   with content-length 0.
2. **With the secret set, `/healthz` would still 503.** `--factory` calls the
   factory with no arguments, so `audit_repository` took its default of `None`,
   and the endpoint's no-repository branch answers 503. There was no concrete
   implementation of the `AuditRepository` protocol anywhere in `src/`.
3. **A later CI run would break it again.** The deploy step wrote a one-line
   env file and scp'd it wholesale over `/srv/services/vcf-ops-mcp/.env`, so
   the moment lab-admin populated that file with `SESSION_SECRET`, the next
   deploy would wipe it.

A fourth defect surfaced while building: `mcp` was pinned only as `>=1.2.0`,
and `mcp` 2.0.0 has since shipped without `mcp.server.fastmcp`. Both the test
extra and the Dockerfile's install list resolved to 2.x, so `import` failed
before any of the above mattered.

The endpoint's 503-when-the-audit-store-is-unavailable behavior was never the
bug. Per the constitution, no tool path ships without its audit write, so a
server reporting itself unhealthy because it cannot record what it does is the
invariant working. The gate was not touched. The audit store got built.

## Proposals (phase 1, blind)

No worker round ran. The three round-5 proposal branches exist but were never
dispatched to completion, never critiqued, and never approved. They are cited
here as input, not as the phase-1 artifacts of this record.

| Source | Branch | Read as |
| --- | --- | --- |
| claude-worker (round 5, unapproved) | `claude/*` round-5 worktree | input |
| codex-worker (round 5, unapproved) | `codex/*` round-5 worktree | input |
| agy-worker (round 5, unapproved) | `agy/*` round-5 worktree | input |

All three independently proposed a durable SQLite-backed repository on the
`/audit` volume. That convergence is a genuine signal and this record agrees
with it. They disagreed with each other, and with this record, on the details
that actually matter, which is where the reasoning below spends its time.

## Decision

### Storage: stdlib `sqlite3`, one file on the `/audit` volume

`SqliteAuditRepository` in `src/vcf_ops_mcp/audit/sqlite_repository.py`, backed
by `/audit/audit.sqlite3` (overridable with `AUDIT_DB_PATH`, which defaults to
that path and should stay unset in the slot). WAL journaling,
`synchronous=FULL`, `temp_store=MEMORY` because the production root filesystem
is read-only, and a bounded busy timeout.

No new dependency. `sqlite3` is in the standard library, so this commits the
service to no storage engine it was not already carrying: the free-space
accounting in `dispatcher/reservations.py` was already written against SQLite
page and WAL-frame arithmetic, and decision 012 already named a SQLite
database with no rotation for Phase 1. Choosing anything else here would have
been the escalation-worthy move, not this.

**Rejected: an append-only NDJSON or text ledger.** It reads well and needs no
library at all, but every reconciliation query becomes a full-file parse, and
"is this attempt closed" becomes a join the code has to implement by hand
against a file that grows without bound. The free-space constants would also
have to be re-derived. Durability is the harder objection: a line-append plus
`fsync` is defensible, but proving a partially written trailing line is
detected and does not corrupt the next read is more work than the query
convenience is worth.

**Rejected: anything requiring a new dependency** (a Postgres client, an ORM).
Out of bounds without escalation, and unjustified for a single-writer ledger
in a personal-lab appliance.

### The ledger is append-only. Reconciliation appends; it never rewrites

No statement in the module updates or deletes a row of `audit_records`.
Closing an unreconciled attempt appends a new `outcome_unknown` record
carrying the original call's identity, the recovery timestamp, and the error
code `attempt_unreconciled_at_recovery`. It sets no latency, because recovery
does not know one.

This is the one place this record goes firmly against a read proposal.
agy-worker's proposal said reconciliation would "bulk-update their status to
`outcome_unknown`". That is the wrong shape for an audit ledger. An UPDATE
destroys the evidence that an attempt was ever recorded and when, which is
precisely the fact a later reader needs, and it makes the storage layer
capable of rewriting history at all. Append-only keeps the attempt and its
terminal record side by side, which is also what the dispatcher already
writes on the happy path: one attempt row, one terminal row, same correlation
id. Recovery producing exactly that shape means one reader serves both cases.

The only mutable row in the database is the single write-probe row, which
carries no audit content.

### An attempt is unreconciled by query, never by cached counter

An attempt is unreconciled if and only if its correlation id has a row with
status `attempt` and no row with any other status. That predicate is evaluated
against committed storage on every call to `unreconciled_attempts`,
`unreconciled_attempt_count`, and `close_unreconciled_attempts`. Duplicate
attempt rows for one correlation id (a prior process retrying its attempt
write) count once, because one call owes one terminal record.

The `audit_records` primary key is a plain `INTEGER PRIMARY KEY` rather than
`AUTOINCREMENT`, and that is a reservation-arithmetic decision rather than a
stylistic one. `AUTOINCREMENT` dirties an additional `sqlite_sequence` page on
every insert, which `DIRTY_PAGES_PER_AUDIT_RECORD` does not reserve: near the
admission threshold a call could be admitted, run its handler, and then find no
reserved room for its terminal commit. The rowid alias is monotonic here
regardless, because the module never deletes a row, so no id is ever reused.
The Codex review on PR #9 caught this too.

`close_unreconciled_attempts` runs in a single `BEGIN IMMEDIATE` transaction:
select, insert one terminal row per open attempt, commit, return the count. It
is idempotent by construction, since after the commit those attempts have
terminal rows. It never infers a successful outcome; there is no code path in
the module that writes `AuditStatus.OK`.

### `is_writable` commits a real write

`is_writable` opens a transaction and commits an upsert into a dedicated
single-row `write_probe` table, under `synchronous=FULL`. A True answer
therefore means the storage layer accepted a durable write, not that the
Python object exists or that a mode bit looked permissive. Nothing weaker
would do: the health gate is built entirely on this answer, and a probe that
cannot fail is a gate that cannot gate.

The probe writes to its own table so it never pollutes the ledger, and it
never appends a synthetic audit record, because an audit log containing rows
that describe no tool call is a worse artifact than a separate probe table.

On a SQLite or OS error the probe drops its connection and returns False. It
does not raise, because "not writable" is a legitimate health answer.
Reads and appends do the opposite: `append_committed` and the count and
enumeration methods raise `AuditStorageUnavailable` rather than degrade. A
record that cannot be committed must never be silently dropped, and a count
that cannot be read must never be reported as zero. "I cannot tell" and
"there is nothing there" are different answers and only one of them is safe.

The connection is reopened lazily on next use after a failure, so an operator
who repairs the volume gets a recovered server without a restart. Reconciliation
is therefore not a boot-time-only concern: the first use after any open
reconciles before the store is allowed to call itself ready. Without that, a
process whose bootstrap failed against a ledger already holding open attempts
would reopen the repaired volume, report writable, answer the health gate 200,
and leave those attempts without terminal records forever. The Codex review on
PR #9 caught exactly that hole. Reads stay side-effect free; the probe and the
append path are what carry the readiness check.

### Composition root: a new module, not a second factory in `app.py`

`src/vcf_ops_mcp/main.py` exposes `create_production_app()`, and the Dockerfile
CMD becomes
`uvicorn vcf_ops_mcp.main:create_production_app --host 0.0.0.0 --port 8000 --factory`.

`create_app(audit_repository=...)` keeps its signature untouched. That argument
is the seam every test uses to substitute a double, and building the store
inside `create_app` would close it. A composition root that lives inside the
thing it composes has stopped being a composition root.

**Rejected: `create_production_app` alongside `create_app` in `app.py`.** It
works and is one file fewer, but it puts the module that must know about the
filesystem, the `/audit` volume, and logging configuration in the same file as
the pure application wiring, and every test that imports `create_app` then
imports that knowledge too.

Bootstrap is synchronous on purpose. `open` plus reconciliation are plain
`sqlite3` calls, they run before the server accepts a single request, and
doing them in the factory rather than in a lifespan hook means the process
reaches its first request with reconciliation already committed and logged.
The async surface of the repository runs its SQLite work in a worker thread
under one lock, which costs nothing real: SQLite admits one writer at a time
anyway.

### Boot posture: degraded and unhealthy, not crash-looping

If the audit store cannot be opened or reconciled, `create_production_app`
logs the exception and returns the application anyway, wired to the
repository. `/healthz` then answers 503 saying the store is not writable, and
CI's health gate fails the deploy.

This is not a weakening of the audit invariant, and the distinction is worth
stating plainly because it looks like one. The invariant is enforced on the
write path, not at boot: with an unwritable store the dispatcher's attempt
write raises and the call is refused before any handler runs, and
`StructuralAuditMiddleware` refuses security-relevant admin writes. Nothing
gets served unaudited either way. What differs is diagnosability. A running
container that reports itself unhealthy and logs why can be inspected; a crash
loop answers the edge proxy with an empty 503 and takes its own logs down with
it, which is exactly the failure this issue spent three rounds behind. The
gate stays honest in both cases, because in both cases the answer is 503.

codex-worker's proposal preferred constructing the app with no repository at
all on a bootstrap failure. Passing the repository is better: it lets the lazy
reopen recover a repaired volume without a restart, and it keeps one code path
instead of two.

### Health endpoint

The 200-if-and-only-if-`is_writable` contract is unchanged. Two things were
hardened around it, neither of which relaxes it:

- A repository whose probe or count raises now yields 503, not a 500. An
  exception escaping the endpoint would have made an unreachable store look
  like a server bug.
- `unreconciled_outcome_unknown_count` reports `null` when the count cannot be
  read. It is never fabricated as 0.

A nonzero unreconciled count does not by itself fail the gate. Those records
exist because reconciliation recorded them, which is the invariant working;
readiness is write capability, and the count is reported for the operator.

## Half A: `SESSION_SECRET`

The value is authored by hand on the slot by lab-admin and is delivered
nowhere else. It is not generated, committed, or defaulted anywhere in this
repository, and CI never sees it.

- `deploy/compose.yml` gains an `environment:` block passing
  `SESSION_SECRET: ${SESSION_SECRET:?set SESSION_SECRET in the slot .env, see deploy/.env.example}`.
  A missing value stops the deploy with a named error rather than starting a
  container that raises and restart-loops.
- `deploy/.env.example` documents the variable, its format (a long random
  single-line string, at least 32 bytes of entropy, `openssl rand -hex 32`),
  and that CI never writes the file.
- The CI clobber bug is fixed with the same convention tool-gateway uses. The
  deploy writes only `images.env`, which it owns and which carries nothing but
  the pinned digest, and passes both `--env-file .env --env-file images.env`
  explicitly on every `docker compose` invocation. Both flags are required
  because `--env-file` replaces Compose's implicit `.env` load rather than
  adding to it, and `images.env` is never auto-loaded at all. The step also
  fails with an actionable message if the host-owned `.env` is absent; it
  checks existence only and never reads the file.

The round-5 proposals suggested self-generating and persisting the secret on a
volume. The principal ruled against that for this dispatch, and this record
follows the ruling: the secret is lab-admin's lane.

## Division of labor

Not applicable. Direct dispatch, single author.

## Dissent

None recorded, because no worker round happened and there was therefore no
losing objection to quote. The places where this record departs from the three
unapproved round-5 proposals are stated in the Decision section above
(append-only versus in-place UPDATE, passing a degraded repository versus
passing `None`, and a separate composition-root module), with the reasoning
for each. Recording them there rather than as dissent is deliberate: those
proposals were input to this decision, not ballots against it.

## Protected paths touched

`src/vcf_ops_mcp/`

## Sign-offs

None. This is a directive-authority record; the `Authority` line above stands
in place of worker sign-offs, per `docs/decisions/README.md`.
