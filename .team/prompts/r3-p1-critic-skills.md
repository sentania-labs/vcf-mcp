# Critic invocation: a 2-2 split on skills ownership

You are invoked as the tiebreaker. Four ballots were cast on this question and
they split 2-2, which is the condition that activates your seat. You are not
being asked to review the round, re-open settled questions, or comment on the
architecture. You are being asked for one vote on one question, with reasoning.

Read the artifacts below from the repository at
`/home/scott/foundry/projects/vcf-ops-mcp` (read-only; you have no worktree and
write nothing).

| Artifact | How to read it |
| --- | --- |
| claude-worker proposal | `git show bfc23827ee5fa47e169a7c0059414c2688d25060` |
| codex-worker proposal | `git show ae239552ae857294c01adcb4901fc943614ebb20` |
| agy-worker proposal | `git show f136b2aa3a13f3f0637e4d5215b37e18df35fbe8` |
| claude-worker critique | `git show 48b68d0746779955358953103e6838c56f5ae174` |
| codex-worker critique | `git show 63b3f4b1d818147caa555f87fe3d61d88ae870fd` |
| agy-worker critique | `git show 4fd8004bb909eb841a1d4e57bcae5bb0c884e366` |
| all four ballots | `git show 1f3d73c:docs/proposals/2/ballots/` (four files) |

The most relevant passages are claude-worker's critique section 1.7 (why
delivery surfaces is oversized) and each ballot's `6-sub` section.

## The question

Question 6 asked how to decompose the Phase 1 build. All four ballots voted 6B:
codex-worker's `contracts.py` interface spine, with two corrections, one of which
is that **the skills surface moves out of the delivery-surfaces slice** because
delivery is oversized. The three main slices are unanimous and are not in
dispute: codex-worker owns the policy and persistence spine including sole
ownership of the dispatcher package, claude-worker owns the VCF read plane,
agy-worker owns delivery surfaces (the Starlette app, MCP binding, admin UI,
container, CI, and the first deploy through the docker.int slot).

**The one open question: who owns the skills surface?**

Skills is a catalog load with digest verification at startup, an index
regeneration check, and four render paths (an MCP resource, a `current` alias, a
prompt, and the `list_skills` / `get_skill` tools for tool-calling-only clients).
It has no dependency on admin session state and no dependency on the VCF client.
It is the smallest independent unit in the tree.

## The four ballots on this question

- **agy-worker: agy-worker.** Voting for itself; it declared that interest. Its
  ballot says skills is "a separate piece" alongside the delivery surfaces it
  owns, and that this "aligns with my explicit documentation of the CI pattern".
- **codex-worker: agy-worker**, as "a separately planned and separately
  reviewable small piece, not as an implicit subdirectory of the delivery slice."
  It adds, verbatim: "If capacity requires another owner, the orchestrator should
  dispatch this piece explicitly rather than allowing shared ownership."
- **claude-worker: codex-worker.** Verbatim: "The spine slice is the smallest of
  the three at 4 to 6 days and delivery is the largest at 8 to 12, so skills goes
  to the light slice and not the heavy one. Splitting it off is the whole point
  of the 1.7 rebalance and putting it back in delivery undoes that."
- **orchestrator: codex-worker**, on the same load-balancing argument.

## What you should weigh, and one thing you should know about me

Both sides agree skills should be a separately planned and separately reviewable
piece. The disagreement is only about whose queue it sits in.

The case for agy-worker: it is already building the application composition and
the MCP binding that skills renders through, so there is real adjacency, and
"separately reviewable" may be enough to prevent the piece from being absorbed
into the delivery tail.

The case for codex-worker: the entire reason skills was moved out of delivery is
that delivery is the largest, highest-variance slice and the one Gate 1 rests on
most directly, since Gate 1 is the human principal connecting a client through
a reverse proxy to a deployed container. Assigning skills back to the owner of
delivery arguably re-creates the imbalance the rebalance was adopted to fix,
whatever the piece is called on the workplan. Against that: skills is genuinely
small, and codex-worker's spine slice already carries the dispatcher, the
credential envelope, the keyring rotation state machine, and API keys, which is
the most correctness-critical work in the round.

**The disclosure you need in order to discount me properly:** I am the
orchestrator, I run on the same model family as claude-worker, and I voted the
same way claude-worker did. That is exactly the configuration your seat exists
to check. I could have voted with the other two and closed this 3-1 without
invoking you, and I did not, because I did not want to settle a question I am a
party to by holding the pen. Weigh my vote as one voice with a known bias, not
as the referee's thumb.

## What to return

One vote: **agy-worker** or **codex-worker**, and your reasoning in enough
detail that a reader in six months can tell whether you engaged with the load
argument or just picked a side. If you think the question is malformed, or that
neither answer is adoptable, say that instead and say why.

Begin your response with a line naming which model actually served this
invocation, if your harness lets you determine that. If you believe you cannot
vote independently on this question for any reason, say so plainly and
self-disqualify; a self-disqualified vote does not break the tie and I will
escalate the unresolved split to the human principal rather than break it
myself.

Do not write any file. Your output is the vote; I commit it into the decision
record verbatim.
