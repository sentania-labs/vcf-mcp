# 010: verbatim-recorded artifacts are exempt from the no-em-dash rule

- **Status:** accepted
- **Date:** 2026-07-25
- **Assignment:** vcf-ops-mcp round 3, the Phase 1 build
- **Orchestrator run:** `gh-issue-2-execution-20260726-011017`
- **Lane:** orchestrator ruling (style-rule scope; no worker round)
- **Workers dispatched:** None
- **Authority:** `CLAUDE.md`, "Escalate to the human principal rather than deciding as a team": style is explicitly the team's call. This record interprets the scope of an existing style rule; it does not amend the rule and does not touch a protected path.
- **Resolves:** the conflict raised independently by two reviewers during the round-3 slice review, recorded in `TEAM-STATE.md` as an item needing an orchestrator ruling

## Why this record has no worker sign-offs

No protected path is touched, no code changes, and no file is edited as a result
of this ruling. `docs/decisions/README.md` requires signatures on records that
authorize work in a protected path. This one authorizes nothing; it says which
of two existing hard rules governs a specific class of file, and the answer is
that neither is weakened.

## Context

`CLAUDE.md` carries a hard style rule: no em-dashes anywhere in the repo, not in
code, docs, or commit messages. Reviewers check it with a repo-wide grep that
catches em-dash and en-dash alike:

    git grep -nP '[\x{2014}\x{2013}]'

That grep currently fails at the repository baseline. Two reviewers found it
independently during the round-3 slice review. The hits are en-dashes, in the
strings `4-6 days` and `8-12` as originally written by the critic, and they are
in exactly two files (paths as of this ruling; the first was later relocated,
unedited, to `docs/history/votes/r3-critic-skills.md` when the retired
foundry team's `.team` directory was deleted, see decision record 015):

    docs/history/votes/r3-critic-skills.md
    docs/proposals/2/ballots/critic-r3-skills-ownership-vote.md

Both files are the same artifact: the cursor critic's tiebreaking vote on skills
ownership, recorded verbatim. The second is the copy committed onto the round
branch so the vote survives branch deletion.

## The conflict

Two rules in this project are both stated as hard, and here they point opposite
ways.

The no-em-dash rule says the character must not appear in the repo.

The verbatim-recording rule, in `roles/orchestrator.md`, says a losing objection
and a critic vote are recorded verbatim, "not paraphrased, not summarized,"
precisely because the referee might be the one who is wrong and the next reader
needs the losing argument in its own words. The critic seat exists to check the
orchestrator's model-family bias. An orchestrator that silently edits the text of
the vote that overruled it has a seat that does nothing.

Editing two characters inside a quotation is a small act with a bad shape. The
point of a verbatim record is that a reader can trust it was not touched, and
that property is not divisible: a record known to have been edited "only where it
did not matter" is a record whose reader must now take the editor's word for what
mattered.

## Decision

**Verbatim-recorded artifacts are outside the scope of the no-em-dash rule, and
are not edited to satisfy it.** The two files above stay byte-for-byte as the
critic wrote them.

The style rule governs prose a resident of this repo authors. A transcription is
not authored prose; it is evidence. The rule was written to keep residents from
producing em-dashed output, and it does that job undiminished when it does not
also reach into quotations of parties who are not bound by it. The critic runs
read-only under a different harness and never agreed to this repo's style rule.

Concretely, the reviewers' check at the time excluded the two directories
holding recorded votes and ballots, using a pathspec of the form
`':!docs/proposals/*/ballots/*'` for one and, for the other, the vote's
directory under the team-tracking directory that has since been deleted
(decision record 015); today the equivalent exclusion is
`':!docs/history/votes/'`:

    git grep -nP '[\x{2014}\x{2013}]' -- . \
      ':!docs/proposals/*/ballots/*' ':!docs/history/votes/'

Note the trailing `*` on the first pathspec rather than a trailing `/`. The
directory-suffix form `':!docs/proposals/*/ballots/'` silently excludes nothing
and the grep still fails; this was verified, not assumed. A literal directory
prefix excludes correctly either way.

**The exemption is narrow and covers transcription only.** Two limits, both
load-bearing:

1. It attaches to the two directories that held recorded votes and ballots,
   `docs/proposals/*/ballots/` and, at the time, the team-tracking
   directory's `votes/` (now `docs/history/votes/`), and to nothing else. A
   verbatim quotation embedded in a decision record or a review marker is a
   normal case of a resident authoring a document; that resident is bound
   everywhere else in the file, and if it must quote a dash-bearing passage it
   uses a marked bracketed transcription note rather than an unmarked edit.
2. A resident's own authored prose does not become exempt by being placed in an
   exempt directory. Dropping original text into `ballots/` to dodge the style
   rule is a violation of this record, not a loophole in it.

## Alternatives rejected

**A marked bracketed transcription note**, replacing each en-dash with a hyphen
and flagging the substitution inline. This was the option `TEAM-STATE.md`
flagged as "probably right" and it is defensible: the edit is disclosed, so
nothing is silent. Rejected because it puts the orchestrator's hand inside the
one artifact whose whole evidentiary value is that the orchestrator's hand is not
in it, and it does so to fix two characters that change no meaning. The
disclosure makes it honest but does not make it necessary.

**A CI check with the exclusion baked in.** Rejected as unnecessary right now:
there is no automated em-dash check in this repo. `.github/workflows/` contains
only `consensus.yml`, and grep over `.github/` and `tools/` finds no dash check.
The rule is enforced by residents and reviewers reading the constitution. So this
ruling has no CI consequence to manage, and adding a check is a separate question
nobody has asked.

**Rewriting the rule in `CLAUDE.md` to say "authored prose".** This is arguably
the cleanest long-term fix, and it is deliberately not taken here: `CLAUDE.md` is
a protected path and constitution edits escalate to the principal. This record
interprets the rule's scope, which is the team's call. If Scott would rather have
the exemption written into the constitution itself, that is his to direct, and
this record is the proposal he would be ruling on.

## Consequences

- The repo-wide dash grep passes at baseline when run with the two exclusions,
  and reviewers should use the excluded form. A future reviewer running the bare
  grep will hit these two files again; this record is the answer to that finding,
  and the finding should be closed by citing it rather than re-litigated.
- No file changes as a result of this record.
- The critic's vote remains checkable against what the critic actually emitted,
  which for a seat that has fired exactly once in this project's history is worth
  more than two characters of style conformance.
