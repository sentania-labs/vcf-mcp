# Re-review: contracts.py at its new SHA (claude-worker)

You are claude-worker. You reviewed `codex/r3-contracts` at `d835437` and
returned **changes-requested**. Your marker is on your own branch
`claude/r3-contracts-signoff` at
`.team/signoffs/codex-r3-contracts-d8354377f0f8.md`, which is checked out in
your worktree. codex-worker has committed a revision on top. Re-review at the
new head.

    git log --oneline codex/r3-contracts
    git diff d835437..codex/r3-contracts

A marker names an exact SHA and stops covering the branch the moment it moves,
so this review produces a **new marker file** named for the new SHA. Do not edit
the old one; it stays as the record of the first round.

## Confirm or deny each, by name

1. **The blocker, claim 2.** `RequestContext.request` is `HttpRequest | None`
   and `RequestState.identity` is `RequestIdentity | None`. The `ToolContext`
   docstring states the extraction obligation (read only from
   `request_context.request.state.identity`; typed deny if `request` is None or
   identity is absent or is not a `RequestIdentity`; no module global; no
   session cache). A test makes absence expressible and asserts it is a
   distinct auditable deny rather than an `AttributeError` on `NoneType`.
   Check the shape against the real SDK again, as you did the first time, not
   against the spike text alone.
2. **Claim 4, reconciliation.** `AuditRepository` now carries what delivery
   needs to build the `/healthz` unreconciled count and the admin list from
   durable storage, and recovery closes `started` rows with no terminal record
   as `outcome_unknown`, never optimistically successful. If codex instead
   declared reconciliation spine-internal, judge whether the named route it
   gives delivery is real and sufficient, and say so either way.
3. **Claim 1, DRAIN versus CANCEL.** The decision-4 rule is carried in
   mechanism: tightening `verify_ssl` from false to true forces CANCEL and an
   admin write cannot silently pass DRAIN for it.
4. **Both nits.** `MUTATING` annotated `frozenset[CapabilityName]` with the
   runtime value still empty, and a no-payload sentinel so a literal `None`
   handler result can be wrapped in `outcome_unknown`.
5. **Nothing regressed.** The five claims you already confirmed still hold:
   the invalidation protocol, capability-based 5B enforcement with `MUTATING`
   frozen and empty, framework neutrality (stdlib imports only), the
   `outcome_unknown` envelope's structural enforcement, and constitution
   conformance (no em-dashes, no credentials, parseable `Co-authored-by:`
   trailer, protected path authorized by record 009).
6. **Scope.** Nothing outside `contracts.py`, `__init__.py`, and
   `tests/test_contracts.py`. No spine implementation smuggled in.

If codex **declined** any requested change, its commit message must say so with
reasoning. Judge the reasoning on its merits; a well-argued decline you accept
is a fine outcome, but an item silently not done is not.

## Rules

- Run the suite yourself and paste the real output:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v`
  Run it read-only in codex's worktree
  (`/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-codex`); make no edit
  there.
- **Withholding is a valid outcome and always was.** Do not sign to be
  agreeable. If the blocker is still open, say so and set
  `result: changes-requested` again.
- Write the marker at `.team/signoffs/codex-r3-contracts-<first-12-of-new-sha>.md`
  with front matter: `reviewed_branch`, `reviewed_sha` (full 40 chars),
  `reviewed_by: claude-worker`, `authored_by: codex-worker`, `timestamp` (read
  it from `date -u`, do not guess), `tests_run`, `result` (`signed` or
  `changes-requested`).
- Commit it on your own branch `claude/r3-contracts-signoff`, already checked
  out in your worktree. Confirm with `git branch --show-current`. Do not create
  a new branch, do not push, do not open a PR.
- No em-dashes anywhere. Trailer on its own physical line:
  `Co-authored-by: claude-worker <claude@team.local>`, verified with
  `git log -1 --format='%(trailers:key=Co-authored-by)'`.
