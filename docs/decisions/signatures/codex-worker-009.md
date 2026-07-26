# Codex worker review of decision 009

1. **Ballot tally: confirmed.** Decision 1 records my 1B vote. Decision 2
   records my 2C vote. Decision 3 records my 3B vote. Decision 4 records my 4B
   vote. Decision 5 records my 5B vote and my yes vote on 5-sub. Decision 6
   records my 6B vote, the spine/read-plane/delivery ownership split I voted
   for, and agy-worker as the separately planned skills owner. Decision 7
   records my 7C-with-payload vote and my no vote on 7-sub, with conditions.
   The result table and decision prose match all of those votes.

2. **Dissents and objections: denied.** My fingerprint-pinning objection is
   present and its substance is not softened, but it is not verbatim. The
   ballot says:

   > Fingerprint pinning also remains underspecified. Normal certificate
   > validation cannot complete a handshake against an untrusted self-signed
   > chain and then perform a post-handshake fingerprint check. Phase 1 should
   > prefer a mounted CA bundle. If direct fingerprint pinning remains required,
   > the workplan must budget a transport implementation that verifies every
   > connection and an explicit, unauthenticated first-trust ceremony.

   Record 009 instead paraphrases that objection and adds a reference to
   claude-worker's three-state design. The record must quote my ballot text
   exactly, marked verbatim, to satisfy the stated preservation requirement.
   My audit-finalization objection is accurately represented in decisions 7
   and 7-sub, but it is also synthesized rather than quoted verbatim.

3. **Concessions: confirmed.** The record does not overstate my critique-round
   concessions. I conceded claude-worker's authentication generation algorithm,
   fixture-synthesis direction, provisioning measurement, and larger estimate.
   The record accurately describes my later ballot changes on SQLite rotation,
   GET-only enforcement, and withholding the result after terminal audit
   failure. It does not claim that I conceded more than I did.

4. **Measurements: confirmed.** Of the named measurements, I personally measured
   the `OpsToken` and `vRealizeOpsToken` 200 responses and the `Bearer` 401
   response. Record 009 and the approved spec state those results correctly. I
   did not personally measure the 517-resource count, 21 adapter kinds, the
   137,808-byte metrics response, or 142 action definitions, so I make no
   first-hand claim about those values. Nothing attributed specifically to my
   recon is misstated.

5. **Amendment 1: confirmed.** The reading is honest. The approved spec states
   report-definitions-only scope, per-target TLS verification disabled for the
   first DEVEL registration while preferring a mounted CA bundle as the
   principal's call, and the decision 7-sub audit-invariant interpretation.
   A bare unconditional approval of that pinned spec can reasonably authorize
   those stated answers. Amendment 1 also preserves the CA bundle and audit
   interpretation as named Gate 1 review items rather than claiming they can
   never be revisited.

6. **My slice acceptance criteria: denied.** Most are buildable and measurable:
   dispatcher ordering and failure tests, the open registration core and
   extension rule, the typed `outcome_unknown` envelope, both mutation-policy
   checks, and end-to-end audit coverage. The free-space criterion is not pinned
   as my ballot required. The workplan says only that accounting must be
   specified numerically, while the spec still says only "a conservative
   free-space threshold." Neither document supplies a numeric reservation,
   defines whether the reservation covers one terminal row, WAL growth and
   checkpoint headroom, or specifies how concurrent admitted calls consume and
   release that reservation. Before implementation, record 009 or its approved
   workplan must state the numeric rule and accounting semantics that the test
   will verify.

WITHHELD

I will sign when my fingerprint-pinning objection is reproduced verbatim and
the free-space admission and reservation rule for my slice is pinned
numerically with concurrency accounting.

## Review after Amendment 2

1. **Condition 1 is met.** I checked the amended quotation character by
   character against my ballot at
   `e191214a9a86c5c674dfa9e7fe7bc7004377925a`. The wording and punctuation
   match exactly, and the reference to claude-worker's three-state design no
   longer appears inside my quotation. I agree that decisions 7 and 7-sub
   synthesize rather than quote my audit-finalization objection, and I do not
   condition my signature on rewriting argumentative decision prose as a
   quotation.

2. **I accept Ruling 1.** It assigns the numeric threshold to the slice owner
   as a value that must be derived, declared, tested, and reported at Gate 1.
   That is a falsifiable obligation and is symmetric with the metrics-cap
   obligation. The added acceptance criterion covers the substantive half of
   my objection: the reservation must account for the terminal row, WAL growth,
   and checkpoint headroom, and must define how concurrent admitted calls
   consume and release capacity. I will derive the number from those semantics
   and make both the derivation and the test reviewable in the implementation.

3. **I have no objection to Ruling 2.** The
   target-configuration-generation and client-invalidation protocol is a shared
   contract among the target repository, client registry, and admin write
   path. Putting it in `contracts.py` during step 1 gives all three slices one
   serialization point before their implementations diverge.

Signed-off-by: codex-worker <codex@team.local> 2026-07-24T22:05:21Z
