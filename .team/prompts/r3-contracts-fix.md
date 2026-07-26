# contracts.py revision (codex-worker), addressing a changes-requested review

You are codex-worker. You authored `src/vcf_ops_mcp/contracts.py` at
`d8354377f0f8deef12fc11862f89fdcc056c940c` on your branch `codex/r3-contracts`,
which is checked out in your worktree. claude-worker reviewed it and returned
**changes-requested**, not a sign-off. The marker is on branch
`claude/r3-contracts-signoff` at path
`.team/signoffs/codex-r3-contracts-d8354377f0f8.md`. Read it in full first:

    git show claude/r3-contracts-signoff:.team/signoffs/codex-r3-contracts-d8354377f0f8.md

It confirmed five of seven claims. Fix what follows, in **one commit** on your
existing branch. Do not rebase, do not amend `d835437`; add a new commit on top.

## Required (the blocker): claim 2, the identity contract types away absence

The reviewer checked the real SDK, not just the spike text: in `mcp==1.28.1`,
`mcp/shared/context.py` declares `request: RequestT | None = None`. Your
`RequestContext.request: HttpRequest` says the value cannot be missing, while
spike 001's "Dispatcher consequence" item 3 requires the dispatcher to fail
closed when it **is** missing. A value that must be rejected when absent has to
be expressible as absent.

Do all of:

1. Type `RequestContext.request` as `HttpRequest | None`.
2. Type `RequestState.identity` as `RequestIdentity | None` (Starlette `State`
   raises `AttributeError` on a missing attribute, which is exactly the
   middleware-did-not-run case).
3. State the extraction obligation in the `ToolContext` docstring, where four
   slices will read it: read identity only from
   `request_context.request.state.identity`; deny with a typed error if
   `request` is None, or `identity` is absent, or it is not a
   `RequestIdentity`; never read a module global; never cache identity on a
   session.
4. Add a test that the absent cases are expressible and are a distinct,
   auditable deny rather than an `AttributeError` on `NoneType`.

## Also required in the same commit (both are cross-slice seams)

**Claim 4, the reconciliation surface.** Decision 7 requires unclosed attempts
be surfaced from **durable** storage: a count in `/healthz`, a list in the admin
UI, and recovery closing `started` rows with no terminal record as
`outcome_unknown`, never optimistically successful. `AuditRepository` exposes
only `append_committed` and `is_writable`, so agy-worker's delivery slice would
have to reach around the contract into your SQLite schema. Add the methods
delivery needs (an unreconciled-attempt count, an enumeration, and a close-out
on recovery), or, if you believe reconciliation is genuinely spine-internal,
state the named route delivery reads it by, explicitly, in the docstring. The
seam has to be decided here because this is the only serialization point.

**Claim 1, DRAIN versus CANCEL selection.** The invalidation protocol is well
built, but nothing says who picks the mode. Decision 4 supplies the one rule
that makes this a security mechanism: flipping `verify_ssl` from false to true
is a security action and an in-flight request must not silently ignore it, so
that edit requires CANCEL. As written `mode` is a free parameter of the admin
write, which is agy's slice. Carry the rule: a helper deriving the mode from
which fields changed is preferred over a docstring sentence.

## Nits, fix both, they are cheap

1. Annotate `MUTATING` as `frozenset[CapabilityName]`, not
   `frozenset[Capability]`, so the test-scoped mutating set containing the
   synthetic capability is type-compatible. Decision 5-sub requires that set to
   run through the real dispatcher. Runtime value unchanged: it stays empty.
2. `ResponseEnvelope` uses `None` to mean "no payload", so a handler result of
   literally `None` cannot be wrapped in `outcome_unknown`. Add a module-level
   sentinel so that is unreachable rather than merely unlikely.

## Scope discipline

Nothing else. Do not start spine implementation; that is your next dispatch.
Do not touch any file outside `src/vcf_ops_mcp/contracts.py`,
`src/vcf_ops_mcp/__init__.py`, and `tests/test_contracts.py`.

If you disagree with a requested change, you may decline it, but you must say
so explicitly in the commit message with your reasoning. Silently not doing one
is the failure mode; the reviewer re-checks all of them at the new SHA.

## Before you commit

- Run the suite and paste the real output in your commit message:
  `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- **No em-dashes anywhere.** Verify: `grep -nP '[\x{2014}\x{2013}]'` over your
  diff returns nothing.
- No credentials, hostnames, tokens, or lab identifiers in the diff.
- Commit with a real trailer, on its own physical line, never a literal `\n`:
  `Co-authored-by: codex-worker <codex@team.local>`
  Verify with `git log -1 --format='%(trailers:key=Co-authored-by)'`; if it
  prints nothing, your trailer is not parseable and the commit must be redone.
- Stay on the branch already checked out in your worktree. Confirm with
  `git branch --show-current` before committing. Do not create a new branch.
- Do not push. Do not open a PR. The orchestrator integrates.

Report the new SHA and, per requested item, whether you made the change or
declined it and why.
