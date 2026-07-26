---
source-ref: 4fd8004bb909eb841a1d4e57bcae5bb0c884e366
source-commit: 4fd8004bb909eb841a1d4e57bcae5bb0c884e366
source-blob: 413bad55dd84d38d04df4210502190518d6d6f75
source-path: docs/proposals/agy-worker-phase1-critique.md
worker: agy-worker
round: round-3
phase: phase2
captured: 2026-07-26
---

# Phase 1 Build Critique (agy-worker)

## Critique of claude-worker (`p1-build-claude.md`)

### Steelman
Claude proposes a structural, unbypassable enforcement of the mandatory dispatcher and the read-only constraint. It achieves dispatcher enforcement by wrapping handlers at registration time, meaning any tool that forgets the dispatcher simply ceases to exist in the FastMCP registry. It enforces read-only behavior via an explicit capability registry rather than HTTP verbs, explicitly checking `target.posture` against a `MUTATING` capability set that is empty in Phase 1. It proposes a strict token generation counter to prevent 401 refresh stampedes and insists on hard-failing the Uvicorn process if the NDJSON audit log fails to write, arguing that this strictly honors the constitutional invariant. Claude also identifies a critical environment truth: the delivered service account is scoped to only four objects, which will silently break Gate 1.

### Attacks
1. **Audit write failure semantics break manageability:** Claude asserts that if the audit `attempt` write fails, the tool call must fail, which is constitutionally correct. However, Claude goes further and says: "A startup check refuses to boot if the audit volume is unwritable, so this surfaces at deploy rather than mid-session." If the server refuses to boot or Uvicorn crashes because the audit volume is full, the Admin UI is taken down with it. The Admin UI is required for diagnostics, target posture changes, and reading the audit log itself. Taking down the Admin UI for a full audit volume turns a manageable disk issue into a total system outage. The audit failure must block *tool execution*, not process startup.
2. **Fixture scrubbing strategy is operationally heavy and fragile:** Claude relies on a manual recorder script where a developer captures payloads, generates synthetic ones through a whitelist approach, and commits them. While it mitigates the blacklist leak risk, this approach practically guarantees fixture staleness. When the API drifts, the friction of manually re-running and re-scrubbing captures will encourage developers to test against old fixtures rather than keeping them updated.
3. **Dispatcher seam creates a sequential blocker:** Claude places the dispatcher at `dispatch.py`, which imports from the store, the target client, and the handlers. Claude correctly admits this is a "genuine seam problem." Whoever writes `dispatch.py` is sequentially blocked until both the store and the client layers are complete.

## Critique of codex-worker (`codex-worker-phase1-build.md`)

### Steelman
Codex divides the project into three horizontal slices centered around formal interfaces (`contracts.py`) rather than vertical features. This approach prevents merge conflicts and breaks the dependency cycle between the dispatcher, the store, and the client. It proposes using SQLite for both data and audit, leveraging standard library tools for transactional consistency, though isolating audit to a separate volume. It implements the token lock generation check similar to Claude, ensuring single-flight authentication on 401s.

### Attacks
1. **The read-only choke point is broken by unverified assumptions:** Codex proposes that the base HTTP transport "rejects every upstream method except GET," and claims a registry test will prove that "its declared upstream verbs are GET." However, Claude's recon proves that three of the four core read families in VCF (querying resources, stats, and alerts) are HTTP POSTs. Codex's verb-based choke point would hard-block the legitimate read traffic Phase 1 is designed to support. Because Codex did not measure the actual API's read verb shapes, its primary enforcement mechanism is factually incompatible with VCF Ops.
2. **Audit rotation into SQLite archives is dangerous:** Codex proposes rotating the audit log into "read-only monthly SQLite archives using SQLite's backup API." This introduces significant operational risk. Backing up an active SQLite database while tool calls are concurrently writing to it can cause locking contention and write timeouts, especially since the audit log is on the hot path for every tool call. A simple append-only NDJSON file, rotated by the host, is vastly safer and avoids SQLite locking completely.
3. **Token lifecycle lock check is incomplete:** Codex's single-flight token check states that on 401, a caller reacquires only if the generation equals the failed snapshot, and then "concurrent callers then reuse the winner's token. Each original call retries exactly once." However, if the new token *also* fails (e.g., credentials revoked mid-session), the concurrent caller will wake up, see a generation change, retry with the new token, and receive a 401. Without a mechanism to track whether a given *request* has already retried once (which Codex does not explicitly mention), this can lead to unbounded retry loops or race conditions during credential invalidation.

## Concessions
- **I was wrong about verb-based read-only enforcement:** In my own proposal, I proposed restricting the client to `GET` only if the posture is read-only. Claude's measured finding that VCF read queries require `POST` completely invalidates my approach. A verb-based gate is unbuildable. I concede to Claude's capability-registry approach for read-only enforcement.
- **I missed the Gate 1 scope blocker:** Claude's discovery that the delivered service account only sees 4 objects is an excellent catch. If we didn't escalate this, Gate 1 would fail confusingly.
- **I was wrong about dispatcher dependencies:** I proposed a vertical slice where the dispatcher was centralized but didn't formalize the interfaces up front. Codex is right that `contracts.py` (policy and persistence spine) is a structurally superior way to organize the work, as it allows parallel development without sequential blockers.

## What the team should do
1. **Read-only enforcement:** Adopt Claude's capability-based registry check in the dispatcher. We cannot use HTTP verbs to gate read/write access.
2. **Audit:** Adopt Claude's NDJSON append-only file for the audit log, as it avoids Codex's SQLite backup locking issues. However, we must explicitly modify Claude's startup behavior: an unwritable audit log must hard-block tool executions (as the constitution demands), but it must **not** block Uvicorn process startup. The Admin UI must remain available for diagnostics.
3. **Architecture & Decomposition:** Adopt Codex's `contracts.py` interface spine. By defining the `ToolContext` and repository protocols first, all three of us can work in parallel without waiting on a centralized `dispatch.py` to be completed.
4. **Token lifecycle:** Adopt Claude's specific generation-counter logic which ensures losers await the new token but do not retry if the generation moved and the request already failed once.
5. **Escalation:** The orchestrator must immediately escalate to lab-admin to widen the `vcf-ops-mcp` service account's role scope to `allowAllObjects`, or Gate 1 will fail.
