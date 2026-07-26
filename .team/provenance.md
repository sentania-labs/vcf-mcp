# Provenance ledger

Join key between a decision record's SHA citation and the in-tree copy of
that content after its source round/doer branch is deleted. See
`bin/team-record-artifact` and `conventions/provenance-README.md` for
the full convention. One row per document recorded via
`bin/team-record-artifact`; a row's `In-tree path` is where that document's
content lives now, and `Source SHA` is the commit a decision record cites.
The row is what makes that citation auditable once the branch holding
`Source SHA` no longer exists in this checkout.

Note for a future run: the framework's `bin/team-provenance-ledger` writes
this header with an em-dash on first use, which violates this repo's
no-em-dash rule. The header was corrected here by hand. The tool only
appends rows after first use, so it does not rewrite this paragraph and the
correction is stable. Fixing it upstream in the framework is a separate,
non-blocking item.

| In-tree path | Source SHA | Source ref | Worker | Round/Phase | Captured |
|---|---|---|---|---|---|
| `docs/artifacts/round-3/phase1/claude-worker-build.md` | `bfc23827ee5fa47e169a7c0059414c2688d25060` | `bfc23827ee5fa47e169a7c0059414c2688d25060` | claude-worker | round-3/phase1 | 2026-07-26 |
| `docs/artifacts/round-3/phase1/codex-worker-build.md` | `ae239552ae857294c01adcb4901fc943614ebb20` | `ae239552ae857294c01adcb4901fc943614ebb20` | codex-worker | round-3/phase1 | 2026-07-26 |
| `docs/artifacts/round-3/phase1/agy-worker-build.md` | `f136b2aa3a13f3f0637e4d5215b37e18df35fbe8` | `f136b2aa3a13f3f0637e4d5215b37e18df35fbe8` | agy-worker | round-3/phase1 | 2026-07-26 |
| `docs/artifacts/round-3/phase2/claude-worker-critique.md` | `48b68d0746779955358953103e6838c56f5ae174` | `48b68d0746779955358953103e6838c56f5ae174` | claude-worker | round-3/phase2 | 2026-07-26 |
| `docs/artifacts/round-3/phase2/codex-worker-critique.md` | `63b3f4b1d818147caa555f87fe3d61d88ae870fd` | `63b3f4b1d818147caa555f87fe3d61d88ae870fd` | codex-worker | round-3/phase2 | 2026-07-26 |
| `docs/artifacts/round-3/phase2/agy-worker-critique.md` | `4fd8004bb909eb841a1d4e57bcae5bb0c884e366` | `4fd8004bb909eb841a1d4e57bcae5bb0c884e366` | agy-worker | round-3/phase2 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/claude-worker-ballot.md` | `a7c210a51f11231d0bd087d0a01a20a047bc55eb` | `a7c210a51f11231d0bd087d0a01a20a047bc55eb` | claude-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/codex-worker-ballot.md` | `ef60f4d20e674e681377a67737662ceab6407191` | `ef60f4d20e674e681377a67737662ceab6407191` | codex-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/agy-worker-ballot.md` | `612bbe6ce7e33be9dabcb153be799c6b1b4ec193` | `612bbe6ce7e33be9dabcb153be799c6b1b4ec193` | agy-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/claude-worker-ballot-q1-q6.md` | `20bca552980521f73908759d6843505ac01a3fdf` | `20bca552980521f73908759d6843505ac01a3fdf` | claude-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/codex-worker-ballot-q1-q6.md` | `e191214a9a86c5c674dfa9e7fe7bc7004377925a` | `e191214a9a86c5c674dfa9e7fe7bc7004377925a` | codex-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/agy-worker-ballot-q1-q6.md` | `75bfc1f67e049d72a7e0011b54c93063ab7a144d` | `75bfc1f67e049d72a7e0011b54c93063ab7a144d` | agy-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/claude-worker-signature.md` | `92cf4a4f6c4cb40c2464a962c80af90a635211dc` | `92cf4a4f6c4cb40c2464a962c80af90a635211dc` | claude-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/codex-worker-signature.md` | `bebc4ac448bb9600acb98c30439ab2d241974450` | `bebc4ac448bb9600acb98c30439ab2d241974450` | codex-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/agy-worker-signature.md` | `27f0e3c06763f5fc93fccbc09d0ad3b0adf8746e` | `27f0e3c06763f5fc93fccbc09d0ad3b0adf8746e` | agy-worker | round-3/phase3 | 2026-07-26 |
| `docs/artifacts/round-3/phase3/codex-worker-withholding.md` | `c3f392c730f472461dd4a7e9e271968f2ae91da2` | `c3f392c730f472461dd4a7e9e271968f2ae91da2` | codex-worker | round-3/phase3 | 2026-07-26 |
