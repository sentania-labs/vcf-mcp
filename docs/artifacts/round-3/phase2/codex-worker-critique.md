---
source-ref: 63b3f4b1d818147caa555f87fe3d61d88ae870fd
source-commit: 63b3f4b1d818147caa555f87fe3d61d88ae870fd
source-blob: 2512aed2e532a17b02ae75ed9148a29475085f76
source-path: docs/proposals/codex-worker-phase2-critique.md
worker: codex-worker
round: round-3
phase: phase2
captured: 2026-07-26
---

# Phase 2 adversarial critique, codex-worker

- **Round:** vcf-ops-mcp Phase 1 build
- **Author:** codex-worker
- **Scope:** critiques of claude-worker and agy-worker only

## Claude-worker proposal

### Steelman

Claude-worker proposes a layered service in which FastMCP can only see tools
created by a registration wrapper, and that wrapper always enters one dispatcher.
The dispatcher resolves identity, authorization, target posture, and audit before
calling thin handlers. Typed domain adapters are the only network path. Read-only
enforcement is capability-based rather than HTTP-method-based, with database,
dispatcher, and grantable-scope defenses. Its client uses a per-target lock and
authentication generation counter to collapse both initial acquisition and a
concurrent 401 storm. It avoids committing captures by generating structurally
similar synthetic fixtures, and it treats audit failure as fail-closed while
using rotation and a low-water mark to avoid reaching that state. This is the
most complete proposal and the only peer proposal with a credible work estimate.

### Attacks

1. **Its structural dispatcher guarantee depends on a private FastMCP inventory
   and a social prohibition.** The raw `mcp` object still exists and accepts
   `mcp.tool()` calls. Comparing the custom registry with
   `mcp._tool_manager.list_tools()` detects a side door only while an undocumented
   private attribute has the assumed shape. A dependency upgrade can make the
   assertion fail to collect, and a test that checks equal names cannot prove
   that the installed callable is the generated wrapper rather than a raw handler
   registered under the same name. Under either condition an unaudited tool can
   become callable. Do not export the raw FastMCP instance to tool modules. Put
   construction and binding in one composition root, expose only the project's
   registrar, and add an end-to-end call test that observes an audit record for
   every listed tool. A private-manager assertion can remain a tripwire, but it
   cannot be the security boundary.

2. **The terminal audit write has an unhandled outcome-ambiguity failure.** The
   proposal writes `attempt`, performs the upstream call, then writes `complete`.
   If disk failure occurs after the upstream response, failing the tool call does
   not undo the call. For Phase 1 reads this causes needless retries and missing
   result status. For Phase 2 mutations it can cause an operator to retry an
   action whose submission succeeded, precisely the `outcome_unknown` problem
   record 001 already recognizes. A startup probe, rotation, and a 100 MB warning
   reduce probability but do not close the race, especially with concurrent calls
   consuming the remaining space. The design needs admission-time capacity
   reservation for both records, bounded concurrency, and an emergency reserved
   append path. Even then, an I/O device can fail between upstream completion and
   terminal append, so the honest terminal state returned to the client is
   `outcome_unknown`, never a generic failure that invites automatic retry. If
   the constitution is read as requiring a durable terminal record under physical
   media failure, that is not implementable and must be escalated rather than
   hidden behind the phrase "fail the call."

3. **The proposed self-signed fingerprint path cannot work as described.** A
   post-handshake fingerprint check cannot run after a TLS context with normal
   verification enabled rejects DEVEL's self-signed chain during the handshake.
   Trust-on-first-use also requires an unverified bootstrap connection, so the UI
   must state that the displayed first fingerprint is not authenticated. The
   clean Phase 1 solution is a mounted lab CA bundle if one exists. Otherwise a
   purpose-built transport must perform explicit fingerprint verification on
   every connection, and this is larger than the estimate implies. A boolean
   fallback to `verify=False` is not equivalent.

4. **The fixture generator still has leakage channels and can destroy the
   contract it claims to preserve.** JSON object keys can be dynamic lab values,
   URLs can contain identifiers in paths and query strings, and error strings can
   embed usernames or hostnames. A generator focused on values can copy all three.
   Preserving array cardinality and string format classes can also preserve
   sensitive topology facts. Conversely, replacing every string independently
   loses equality relationships such as a resource ID repeated in a link, which
   means pagination and identity parsers are no longer tested against a coherent
   contract. The generator needs an explicit allowlist of response schema paths,
   deterministic pseudonyms that preserve references, rejection of unknown keys
   and value classes, and a proof test that no raw capture token appears in output.
   Captures must live outside the repository worktree entirely, not merely under
   a gitignored directory where `git add -f` can defeat the control.

5. **The token state machine is single-flight only within one live client
   object.** Editing a target invalidates the process registry, but in-flight
   requests retain the old object. The replacement client and old client can
   concurrently acquire independent tokens, and the old request can continue
   using superseded credentials or TLS policy after the administrator believes
   the edit took effect. The measured appliance tolerates sibling tokens, which
   makes this race quiet rather than safe. Target generations must be checked
   before retry and before returning a result, old clients must be marked closed,
   and target edits need defined drain or cancellation semantics. The proposed
   authentication generation counter correctly solves a 401 storm inside one
   object, but not configuration replacement around it.

6. **The capability registry's empty Phase 1 mutation set does not test the
   decisive branch.** Asserting `MUTATING == frozenset()` proves that Phase 1 has
   no declared mutation. It does not prove a future mutating capability is denied
   on read-only and prod targets. Add a test-only mutating capability now and run
   it through the real dispatcher against read-only, actions-enabled devel, and
   prod fixtures. Otherwise Phase 2's first mutation both activates and tests the
   choke point, which is too late.

7. **The module ownership plan creates the collision it identifies.** Splitting
   `capability.py`, audit semantics, and final assembly of `dispatch.py` across
   residents means three branches must agree on ordering, error types, and record
   fields at the highest-risk seam. "Assemble last" shifts integration work to
   the orchestrator, which is forbidden to write code. One resident must own the
   dispatcher package and publish narrow protocols first. Domain and store owners
   implement against those protocols without co-owning the choke point.

## Agy-worker proposal

### Steelman

Agy-worker proposes a compact Starlette and FastMCP application with clear file
ownership: one client for URL, TLS, and tokens; thin family-specific tools; a
SQLite encrypted target store; hardened admin routes; and a central audited
dispatcher. It correctly keeps target configuration out of deployment, fails
closed when the keyring is unavailable, scopes TLS behavior per target, uses
fixture-backed CI, and explicitly acknowledges that fixture scrubbing and audit
disk exhaustion are dangerous. Its small decomposition could be easy to begin
implementing if the missing contracts were supplied.

### Attacks

1. **The read-only choke point makes Phase 1's required reads impossible.** It
   rejects every non-GET for a read-only target, but DEVEL measurements show
   `POST /api/resources/query`, `POST /api/resources/stats/query`, and
   `POST /api/alerts/query` are reads and return 200. This is immediate
   over-blocking. HTTP verbs are also not semantic authority, so the rule would
   under-block any mutating GET exposed by this or a future API. An endpoint
   allowlist in the generic HTTP client would merely duplicate domain knowledge
   and drift. Enforcement belongs to the mandatory dispatcher and a default-deny
   capability classification, with an independent prod hard block.

2. **The proposed 401 lock still produces N sequential acquisitions.** Each
   failed caller waits for the lock and then "calls acquire". Nothing says it
   captures and rechecks a token generation, so N requests that used one expired
   token acquire N new tokens one after another. The same double-check omission
   can affect initial acquisition. The fix is the generation algorithm in
   claude-worker's proposal: capture generation before sending, recheck under the
   lock, let only the matching generation acquire, and retry once. Reauthentication
   must trigger on exactly 401, not 403, and target replacement still needs a
   separate generation as described above.

3. **Its audit design cannot meet its own invariant.** Checking writability
   before execution does not reserve space. The append can still fail after an
   upstream call, leaving no result status and returning an error for work that
   happened. Host logrotate is also unsafe unless the application detects rename
   and reopens its file descriptor; otherwise it continues writing the rotated
   inode. The proposal needs pre-execution attempt durability, terminal-capacity
   reservation, application-aware rotation or a durable store, explicit
   `outcome_unknown`, and admission shutdown on audit degradation.

4. **"Sanitizes hostnames, tokens, and passwords" is a blacklist that will
   leak.** Live responses can contain usernames, email addresses, IP addresses,
   FQDNs in URLs, adapter names, resource names, UUIDs, certificate details, and
   reflected request values at arbitrary depths. Headers and HTML error bodies
   are additional leak surfaces. Its own risk section admits the defect but
   supplies no acceptance criterion, so the test strategy is not shippable.
   Generate allowlisted, referentially coherent synthetic contracts from
   outside-worktree captures, reject unknown paths, and scan the result. No raw
   capture should ever be staged.

5. **The persistence decomposition is too coarse and the schema is incomplete.**
   A single `store.py` owns migrations, target CRUD, encryption, keyring state,
   API-key digest storage, revocation, admin session state, and possibly audit
   views. Yet the concrete schema lists only targets and credentials. It omits
   API keys and their scopes and target allowlists, schema migration state,
   key-version metadata needed for rotation, and the mechanism by which the UI
   views a JSONL audit log. Parallel work on admin, dispatcher, and store will all
   collide on this file and invent incompatible interfaces. Split store domains
   behind protocols and assign one owner to migrations and composition.

6. **`verify_ssl` as a boolean makes the insecure lab path sticky.** Passing
   `False` to one target avoids global disablement, but it still removes server
   authentication for that target and exposes credentials and tokens to a local
   network attacker. Use system trust or a mounted lab CA bundle. If fingerprint
   pinning is selected, model it as a separate state with explicit bootstrap and
   rotation behavior, not a boolean.

7. **It chooses the wrong auth scheme after the question was already settled.**
   Compatibility with a reference client's legacy spelling is not a reason to
   diverge from decision 006. Send `OpsToken`, the canonical 9.x form. This is a
   narrow defect because both aliases measured 200, but knowingly contradicting
   the record creates needless diagnostic variance.

8. **The 3 to 4 calendar-day estimate is wrong by several multiples.** The
   proposal assigns 1 to 2 days to the registry and all read tools, while that
   scope includes crypto and rotation semantics, migrations, API keys, four
   drifting API families, pagination, projection and result caps, HTML-aware
   errors, concurrent token tests, and synthetic contracts. The remaining 1 to
   2 days allegedly cover FastMCP identity propagation, hardened admin sessions
   and CSRF, audit durability, containerization, CI, external slot provisioning,
   deployment, and Gate 1 debugging. Claude-worker's 15 to 21 dispatch-days is
   the credible order of magnitude. Agy-worker's estimate is not a schedule with
   risk; it is a list of major features counted as if they were file creation.

## Concessions

Claude-worker is better than my Phase 1 proposal on three material points. It
measured the delivered service account's object scope and identified a Gate 1
provisioning failure that I missed. It also replaced the vague idea of sanitized
fixtures with a no-raw-capture synthesis pipeline, which is the right direction
even though its generator needs tighter controls. Finally, its authentication
generation counter is more precise than my earlier single-flight description and
should be adopted.

Claude-worker also estimated the entire deliverable rather than only the happy
path through the core modules. Its estimate exposes sequencing and deployment
variance that mine understated. Agy-worker was right to call out audit disk
exhaustion as an availability hazard, even though it did not solve the hazard,
and its preference for per-target TLS configuration is correct as far as it goes.

## What I now think the team should do

The synthesis should use claude-worker's broad architecture, with corrections:

1. Give one resident sole ownership of the mandatory dispatcher package,
   including capability classification, ordering, audit protocol, and wrapper
   registration. Publish protocols first so store and domain work can proceed in
   parallel without co-editing the choke point.
2. Enforce read-only by default-deny semantic capabilities, never HTTP method.
   Exercise a test-only mutation through the Phase 1 dispatcher now. Keep the
   prod hard block independently in schema and dispatcher policy.
3. Use the authentication generation counter, retry exactly once on 401, never
   on 403, and add a separate target-configuration generation with drain or
   cancellation on edits.
4. Write the attempt audit record before execution and reserve terminal-record
   capacity per admitted call. Stop admission below a conservative threshold.
   Treat a post-upstream terminal-write failure as `outcome_unknown` and prohibit
   automatic retry. Escalate if the invariant is expected to survive physical
   storage failure, because software cannot promise that.
5. Keep raw captures outside the worktree. Generate fixtures through a
   path-allowlisted schema with deterministic pseudonyms, reject unknown fields
   and dynamic keys, preserve reference equality, and scan generated artifacts.
6. Prefer a mounted lab CA bundle. Do not ship `verify=False` as the ordinary
   answer. Treat fingerprint pinning as its own implementation slice only if a
   correct transport and explicit first-trust ceremony are budgeted.
7. Plan against roughly 15 to 21 dispatch-days plus external provisioning
   latency, then cut a thin Gate 1 vertical slice before filling every family.

This differs from my Phase 1 proposal mainly in adopting claude-worker's more
precise token algorithm, synthetic-fixture direction, provisioning finding, and
larger estimate. It differs from claude-worker by rejecting shared ownership of
the dispatcher and by requiring explicit handling of audit completion ambiguity
and target-edit concurrency before those seams become action-bearing.
