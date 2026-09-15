# Roadmap, vcf-mcp

Plain-language status for the captain. This is a snapshot as of 2026-09-15,
not a promise of dates. When this disagrees with `README.md`, `AGENTS.md`, or
a decision record, those win; update this file instead of trusting your
memory of it.

## What's built and working

Nine built-in product packs (Operations, vCenter, NSX, SDDC Manager,
Operations for Networks, Fleet Lifecycle, SDDC Lifecycle, Log Management,
vSAN Data Protection) plus the read-only `/vcf/mcp` management surface are
wired and published through `v0.4.0`. The admin console covers registering
targets, editing credentials and CA trust, minting and revoking API keys,
verifying a target before it is stored, appliance-wide additive CA trust,
tabbed navigation, safe target deletion with key-blast-radius preview, and a
platform-controlled admin recovery ceremony for a lost console password.
Every tool call is audited. All 27 accepted decision records match what is
actually in the code; see `docs/decisions/` for the trail and `README.md` for
the full capability list, that file owns the detail so it is not repeated
here.

All 8 issues ever filed against this repository are closed, and both closed
recently (admin recovery and target deletion) are the two build items the
previous open-issue review flagged as still outstanding. There is no open
issue and no open GitHub milestone right now. This is a clean state, not a
stalled one.

## What's next, in priority order

1. **Operator verification against the devel appliance.** Everything above
   has only been proven against synthetic fixtures. `README.md`'s "Prototype
   boundary" section and `docs/PROTOTYPE.md`'s "Operator verification still
   required" section list, in detail, what cannot be proven without reaching
   the lab: whether the tool calls actually match the real product API
   shapes and permissions, whether TLS handshakes succeed against the lab CA
   chain, whether the reverse proxy passes Streamable HTTP correctly, and
   whether credential decryption and audit survive a real container
   restart. This is next because it is the only thing standing between "the
   fixtures pass" and "this actually works on your hardware," and every
   later step depends on knowing that first. Read-only recon against the
   devel appliance is already allowed for this; no captain approval is
   needed to start it.
2. **Phase 2 gate approval for live action execution.** Once read-only
   behavior is confirmed against devel, the actions framework (execute an
   action, poll it, plan-then-apply) still needs the captain's explicit
   go-ahead before any agent runs it against a live appliance, and it can
   never run against the production appliance. This is deliberately gated
   behind item 1: there is no reason to authorize action execution before
   read-only behavior against real hardware is even confirmed.
3. **A tagged release that matches the working tree, then routine
   maintenance.** `v0.4.0` already contains everything on `main`, so there is
   currently no backlog of unreleased work. This item is a placeholder for
   the normal cycle: cut a new tag whenever new work lands, rather than
   leaving fixes sitting on `main` unreleased the way the previous open-issue
   review found `v0.3.1` doing.

## Deferred or rejected, and why

- **Per-endpoint token-budget warnings and install refusal.** Named
  explicitly in `README.md`'s "Prototype boundary" as deferred. Not started,
  no target date.
- **Fingerprint pinning for operator packs.** Named explicitly in
  `README.md` as "intentionally excluded" from the pack trust model. This is
  a rejection, not a gap: the signed-and-verified OCI distribution path
  (cosign, pinned workflow identity, pinned issuer) was judged sufficient
  without it.
- **Executing actions against the production appliance.** Structurally
  blocked, not merely deferred. `AGENTS.md` states the production appliance
  may only ever be registered read-only until the captain personally flips
  that. This is not on any build queue; it is a standing rule.
- **Changing the additive appliance-CA trust model.** Considered and closed
  in `docs/decisions/024-additive-appliance-ca-trust.md` (captain decision,
  2026-08-26). Revisiting it would be a new security decision, not leftover
  work.

## Where this came from

Repository state (`README.md`, `AGENTS.md`, `docs/decisions/`,
`docs/PROTOTYPE.md`, commit history, and the six published releases through
`v0.4.0`) and the current GitHub issue tracker (0 open issues, all 8 closed).
A 2026-09-08 firstmate open-issue assessment was read last as background; its
two recommended work packages (admin recovery and safe target deletion) have
both since shipped and are reflected above as done, not as pending.
