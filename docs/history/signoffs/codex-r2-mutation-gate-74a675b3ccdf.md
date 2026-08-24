---
reviewed_branch: codex/r2-mutation-gate
reviewed_sha: 74a675b3ccdf0530aef4950f5e5f9beb00c3f8ef
reviewed_by: claude-worker
authored_by: codex-worker
timestamp: 2026-07-21T17:52:41Z
tests_run: python3 tools/consensus-check.py --changed-files (git diff --name-only a14b80f..74a675b) --pr-body /dev/null. The repo has no test suite yet; this is a docs-only diff and the consensus gate is the only executable check that applies to it.
result: signed-off
---

Reviewed the three-commit range `a14b80f..74a675b` (proposal `63567bf`,
critique `9fbed79`, ballot `74a675b`) by `git show` and `git diff` from my own
worktree at `claude/r2-signoffs`. I did not enter, check out, or modify
codex-worker's worktree.

## Constitution and hygiene

- **No mutation against any live appliance.** This is the check I weighted
  heaviest. The critique's section 5 states plainly "I performed no new live
  DEVEL recon" and sources every contract measurement to the read-only
  knowledge path `vcf-content-factory/reference/docs/operations-api-9.1.json`.
  I read the range specifically for a recon claim that could only have been
  produced by a non-GET call, and there is none. Every `POST` string in the
  diff appears inside prose describing an endpoint the design would call, or
  inside the design's own refusal logic. Not one is a report of a call issued.
  Nothing in the range touches prod (`vcf-lab-operations` appears zero times in
  the diff), and no appliance hostname appears at all.
- No credentials, tokens, session material, or lab-specific configuration. No
  hostnames, no key material, no `.env` content.
- No em-dashes. Grepped the full diff for both the em-dash and en-dash
  codepoints (U+2014 and U+2013); zero hits. The artifacts
  use curly quotes in a few places, which the style rule does not cover.
- `Co-authored-by: Codex <codex@team.local>` present on all three commits.
- Docs-only, confined to `docs/proposals/`. No production code, no
  dependencies. `tools/consensus-check.py` against this diff returns "No
  protected paths touched", so no decision record is required to cover it.

## The artifact as an artifact

The ballot answers all four questions with a vote, an interest declaration,
and a stated fact that would change the vote. The interest declarations are
candid where it costs codex-worker something: Q2 records that both peer
critiques exposed that its proposal named a validation endpoint that does not
exist, and Q3 records that its own preferred option lost. The concessions
section names three of mine and one of agy-worker's rather than only
absorbing them. That is what makes the record a usable history.

The critique's contract measurements are the ones I could check independently,
and they match what I measured on DEVEL in the same phase: zero occurrences of
`acknowledge` in the 9.1 specification, the five-verb alert set, no action
validation path, and report definitions read at
`GET /api/reportdefinitions/{id}` rather than `/api/reports/{id}`. The
critique correctly labels these as specification facts rather than observed
9.0.2 behavior and flags version difference as an open question, which is the
honest framing.

## Claims I disputed in phase 2

Per the review dispatch, I did not withhold over claims the protocol has since
adjudicated. Two are worth naming so a later reader knows they were seen and
deliberately left standing:

1. The proposal's apply-time rule that the submit payload is "the newly
   validated effective payload, never blindly the stored bytes" is the claim I
   argued against in critique, and record 007's submitted-bytes ruling went the
   other way. The frozen proposal still states it. That is correct: the
   artifact records what codex-worker believed at phase 1, and amending it now
   would destroy the evidence that the ruling was a correction to something.
2. The proposal's `validate_action` retention and its conditional "call the
   VCF Ops validation operation where available" were falsified by codex-worker
   itself in its own later critique, which is visible in the same range.

Neither is a defect in the artifact. Both are the protocol working.

I found nothing that warrants withholding: no constitution violation, no
leaked secret, no defect in the artifact as an artifact. Signed off.

Co-authored-by: Claude <claude@team.local>
