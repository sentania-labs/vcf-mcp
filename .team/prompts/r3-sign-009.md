# Sign or refuse to sign decision record 009

The principal approved `docs/proposals/2/` on GitHub issue #2 at
2026-07-24T21:41:47Z with the single word `approved`. Implementation is
authorized. Before any code is dispatched, record 009 needs sign-offs from all
three doers, because it governs the protected path `src/vcf_ops_mcp/`.

You are one of those three. Your branch `WORKER/r3-signoffs` is already checked
out in your worktree at `1d44971`. Work there.

## Read first

- `docs/decisions/009-phase1-build-synthesis.md`, the whole record, including
  the new **Amendment 1** at the top.
- `docs/proposals/2/SPEC.md` and `docs/proposals/2/WORKPLAN.md`.
- Your own ballot at `docs/proposals/2/ballots/WORKER-r3-p1-ballot.md`, and
  your own proposal and critique, so you can check the record against what you
  actually said.

## Do not just "sign off". Confirm or deny each of these specifically

Answer every one by name. A denial is a completely valid and useful outcome and
is worth more to this team than a signature you did not earn. The last round's
signature dispatch found two real defects in the orchestrator's own record
because a worker actually checked rather than rubber-stamping.

1. **Your ballot is tallied correctly.** For each of the seven questions plus
   the sub-questions, the record's result table and prose match how you actually
   voted. Name any question where it does not.
2. **Your dissents and objections are recorded verbatim, and not softened.**
   Where you lost, check the quoted text against your ballot character by
   character. The previous round's signer caught an unmarked truncation of its
   own quote. Look for that.
3. **Your concessions are not overstated.** The record quotes concessions from
   the critique round. If it makes you concede more than you conceded, say so.
4. **No measurement is misstated.** The record cites live measurements against
   DEVEL (517 objects, 21 adapter kinds, 137,808 bytes for one resource,
   142 action definitions, the `OpsToken` header result). If you measured any of
   these and the record has it wrong, say so.
5. **Amendment 1's reading of the principal's approval is honest.** This is new
   and no worker has seen it. The orchestrator read a bare `approved` on a spec
   that states its own answers to three open questions as approving those stated
   answers: reports definitions-only, TLS verification off for the first DEVEL
   registration with a CA bundle preferred and still the principal's call, and
   the audit invariant reading of decision 7-sub. **If you think a bare
   `approved` cannot carry one of those three, say which and why.** The
   orchestrator wrote this reading and is the wrong party to be the only one
   checking it.
6. **The acceptance criteria for your own slice are buildable as written.**
   Read your slice in `WORKPLAN.md`. If a criterion is ambiguous, unmeasurable,
   or assumes something that has not been verified, name it now rather than
   discovering it mid-build. This is your last cheap chance.

## Deliverable

One commit on your branch adding exactly one file:

    docs/decisions/signatures/WORKER-009.md

Its content:

- Your six numbered answers, each confirmed or denied with specifics.
- Then, if and only if you are signing, one line in exactly this form, with the
  real current UTC time (run `date -u +%Y-%m-%dT%H:%M:%SZ`, do not invent it):

      Signed-off-by: WORKER <SHORTNAME@team.local> 2026-07-24T00:00:00Z

  Signing means you accept 009 as the team's decision. It does not mean you
  agreed with it. A worker whose objection lost still signs, and its dissent is
  already recorded verbatim.

- If you are **not** signing, write `WITHHELD` in place of that line and state
  exactly what would have to change for you to sign.

## Commit hygiene, checked before integration

- Trailer: `Co-authored-by: WORKER <SHORTNAME@team.local>`, on its own physical
  line at the end of the message. Write a real multi-line message; do not write
  literal `\n` escapes into it, which collapses the message to one line and
  makes git fail to parse the trailer. Verify yours with:
  `git log -1 --format='%(trailers:key=Co-authored-by)'` and confirm it prints
  your line.
- Stay on the branch already checked out in your worktree. Do not create a new
  branch. Confirm with `git branch --show-current` before you commit.
- No em-dashes anywhere. Hard repo rule.
- Do not push. The orchestrator integrates.
- Do not write any code. This dispatch is a signature, nothing else.
