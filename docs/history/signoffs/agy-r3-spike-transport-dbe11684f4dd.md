---
reviewed_branch: agy/r3-spike-transport
reviewed_sha: dbe11684f4dd5d2dbe1ef9202e100d9751308430
reviewed_by: claude-worker
authored_by: agy-worker
timestamp: 2026-07-25T20:15:00Z
tests_run: re-measured the recorded evidence from this worktree, dig vcf-ops-mcp.int.sentania.net and curl -vI https://vcf-ops-mcp.int.sentania.net. No repo test suite exists yet; the diff is docs-only.
result: signed-off
---

# Spike 002, Streamable HTTP through fleet-caddy

Signed off with three recorded deficiencies, none of which changes the verdict.
The BLOCKED conclusion, the refusal to substitute a local proxy, and the
blast-radius call are all correct. Details below, including one piece of
evidence in the document that no longer reproduces.

## What I checked

**The blocker diagnosis and its scope.** Correct, and correctly scoped to the
caddy half of the handoff. I re-ran the two facts I can reach from this
worktree. `dig vcf-ops-mcp.int.sentania.net` still resolves via CNAME to
`docker-proxy.int.sentania.net` (172.16.3.33), matching the document. There is
no route to a backend for this host, so the question the spike existed to
answer remains unanswerable, exactly as recorded.

**Deficiency 1, the headline symptom is now stale and the document is
undated.** The document states the proxy "drops connections to this host during
the TLS handshake (`SSL_ERROR_SYSCALL` upon Client Hello)". That does not
reproduce today. My `curl -vI https://vcf-ops-mcp.int.sentania.net` completed
the TLS handshake, negotiated HTTP/2, and got back `HTTP/2 503` with
`server: Caddy`. Both symptoms are consistent with the same underlying fact
(no per-slot config, therefore no upstream), and the most likely explanation is
that Caddy had not yet issued a certificate for the name when agy-worker
measured it and has since. So the diagnosis survives, but a reader next week
will act on a symptom that is no longer what the endpoint does, and the
document carries no measurement date to warn them. When this spike is re-run,
it needs a "measured on <date>" line and this observation corrected.

**Deficiency 2, Question 1 is under-answered as committed.** The dispatch asked
whether the lab handoff facts exist. The document covers DNS, the slot
directory, and the caddy config, but never mentions `DOCKER_DEPLOY_KEY`. The
orchestrator's BLOCKED marker records that the deploy key is present in repo
Actions secrets, so the deploy half of the handoff did land and only the caddy
half is missing. That is the fact that makes the blocker narrow rather than
broad, and it is missing from the spike artifact itself. I could not verify the
secret independently (no access), so I am flagging the omission, not the claim.

**Deficiency 3, the blast radius is right but stated one-sided.** The document
correctly names the delivery slice's end-to-end proxy verification as blocked
and correctly says the delivery slice can no longer assume the proxy passes
Streamable HTTP intact. It never states what is *not* blocked. The
orchestrator's marker does ("the spine, the read plane, `contracts.py`, skills,
and the admin UI all proceed"), and that is the load-bearing half for anyone
deciding whether to keep building. Read alone, this document is vaguer about
scope than the evidence supports. It also does not name Gate 1's connect step
explicitly, though "hard blocker for the end-to-end proxy test" implies it.

**Did it honestly refrain from substituting an answer?** Yes, and this is the
best thing about the document. Buffering, idle timeout, and header forwarding
are each marked "Not tested" with the structural reason, and reconnect
likewise. The Clean Up section states plainly that no throwaway container and
no local test infrastructure were stood up, because it was told to test the
real proxy only. A local nginx or caddy standing in for fleet-caddy would have
produced numbers that looked like answers and were not, and the author did not
do that. Refusing to manufacture a result is the correct outcome here.

**Nothing improperly committed.** The commit is a single 28-line doc and
nothing else. No credentials, tokens, keys, or session material. The only lab
identifiers present are hostnames and an internal RFC1918 address, which are
already in the repo's docs and are not secrets. No protected path touched.

**Commit trailer.** Correct this round:
`Co-authored-by: agy-worker <agy@team.local>`. The previous round's
`Antigravity <agy@team.local>` defect is not repeated.

**No em-dashes.**

## Why this is a signature and not changes-requested

All three deficiencies are documentation completeness, not a wrong conclusion.
The verdict, the refusal to fake an answer, and the scoping are what the round
branch actually needs from this artifact, and the orchestrator's BLOCKED marker
on the round branch already carries the two missing facts. The blocked marker
already requires this spike to be re-run once the caddy config lands. The three
corrections above belong to that re-run, and this sign-off is the durable
record of them.

Signed off.
