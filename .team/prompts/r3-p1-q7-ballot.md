# Round 3, phase 3: supplementary ballot, question 7

Your six-question ballot is cast and counted. Do not re-open it. This is one
additional question, and it exists because claude-worker's scope check correctly
identified a hole that the six questions routed around, and because I agree with
its assessment that this is a return value and an error type at the choke point
which must be decided before the dispatcher's first commit rather than picked
unilaterally by whoever writes it.

## Results so far, for your context only

| Question | Result |
| --- | --- |
| 1 (audit unavailability blocks startup?) | **1B**, 4-0 |
| 2 (audit storage) | **2C**, 3-1, agy-worker dissenting for 2A |
| 3 (fixtures) | **3B**, 3-1, agy-worker dissenting for 3C |
| 4 (retry bound) | **4B**, 4-0 |
| 5 (enforcement predicate) | **5B**, 4-0; **5-sub yes**, 4-0 |
| 6 (decomposition) | **6B**, 4-0; slices: codex spine, claude read plane, agy delivery, 4-0 |

Skills ownership split 2-2 and is with the critic. It is not your question now.

1B carries a rider I adopted as binding, from claude-worker and independently
from codex-worker: while audit is degraded, security-relevant **admin writes**
(register or edit a target, change posture, mint or revoke a key, rotate the
keyring) fail closed exactly as tool calls do. The admin UI stays up for
diagnosis and reading, not for unaudited change.

## Question 7: what does the dispatcher return when the TERMINAL audit write fails after the upstream call already succeeded?

Settled and not in scope: the **attempt** record is written and committed before
the handler runs, and its failure refuses the call. Nobody disputes that. This
question is only about the tail, where the adapter has already run, the appliance
has already served the read, the durable attempt row already names who called
what against which target with which argument digest, and the finalizing write
then fails.

- **7A.** Withhold the result. Return `audit_unavailable`. The durable `started`
  row remains for reconciliation. (codex-worker's proposal, "Request data flow"
  section.)
- **7B.** Return the result. Mark the call `unfinalized` in memory and surface a
  reconciliation count in `/healthz` and the admin UI. (claude-worker's critique
  1.4: the read already happened, the caller can re-call, withholding does not
  un-read the data and does not improve the audit record by one byte, so it
  converts a transient audit-store problem into data loss for the user while
  leaving the security posture exactly where it was.)
- **7C.** Return a typed **`outcome_unknown`** terminal state that is neither a
  success nor a generic failure, explicitly prohibit automatic client retry,
  force readiness false, and surface the call for reconciliation. Whether the
  result payload accompanies it is part of your vote: say `7C-with-payload` or
  `7C-without-payload`. (codex-worker's critique attack 2 and its ballot
  objection: for Phase 1 reads a generic failure causes needless retries and
  missing status, and for Phase 2 mutations it can make an operator retry an
  action whose submission succeeded, which is exactly record 001's
  `outcome_unknown` problem.)

Engage with all three. In particular:

- 7B's case is strongest for Phase 1, which is reads only, where re-calling is
  free and withholding is pure loss. 7C's case is strongest for Phase 2, where
  the same code path carries mutations and an ambiguous outcome that looks like
  a failure invites a double-submit. Say whether you think Phase 1 should adopt
  the shape it will need in Phase 2, or adopt the shape that is right for reads
  now and change it later. **A change later is a change to the choke point**,
  which is the file this team has spent two rounds making hard to change.
- codex-worker raised, and I am putting to all three of you rather than deciding
  alone, the claim that if the constitution's audit invariant is read as
  requiring a durable **terminal** record even through physical media failure,
  that is not implementable in software and must be escalated to Scott rather
  than papered over with the phrase "fail the call". Vote `escalate: yes` or
  `escalate: no` and say why. My provisional reading, which you should feel free
  to attack: the invariant is satisfied by the pre-execution attempt record,
  which is durable before anything happens, and the terminal record is metadata
  about an event that is already recorded, so no escalation is required. If you
  think that reading is self-serving, say so.

State your vote, your reasoning, and your interest, exactly as before. Append it
to your existing ballot file as a new `## Question 7` section, or write
`docs/proposals/<you>-r3-p1-q7-ballot.md`, and commit it to your branch with a
`Co-authored-by:` trailer. This is a short question and a short dispatch; do not
re-litigate questions 1 through 6 and do not take new recon.
