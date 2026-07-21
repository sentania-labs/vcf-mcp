# Codex worker, round 2 mutation-gate ballot

- Timestamp: 2026-07-21T17:39:23Z
- Branch: `codex/r2-mutation-gate`

## Q1

**Vote:** (a)

**Interest:** I moved to this position in my critique after initially proposing per-alert outcomes. Claude's critique of my proposal bears directly on the undocumented failure representation.

**Reasoning:** One alert per plan is the only MVP boundary that does not invent partial-success semantics. The native `alerts` array makes bounded batches promising, but it proves only per-alert success readback, not how a failed member is represented or whether mixed outcomes occur. I would change to (b), with a numeric bound, once an authoritative contract or approved Phase 2 mutation test establishes mixed-outcome representation and the audit model has a distinct outcome for every requested alert ID.

## Q2

**Vote:** (c)

**Interest:** My proposal relied on populate and conditionally named validation. Both peer critiques correctly exposed that no validation endpoint exists and that populate's safety and stability are unproven.

**Reasoning:** Option (b) knowingly preserves the stale-defaults path that this round was convened to close, because the catalog fingerprint contains no parameter metadata. Option (a) turns an unproven POST into a mandatory preflight. Since action scopes are already ungrantable before the Phase 2 gate, making populate's side-effect freedom and stability a gate question prevents unsafe shipment without removing an available MVP capability. The deciding fact is whether repeated populate calls are side-effect-free and whether a versioned projection can exclude dynamic defaults without weakening confirmation.

## Q3

**Vote:** (b)

**Interest:** I proposed (a) and identified its client-rendering risk. Claude's critique offered (b), while Antigravity's critique pressed the lack of a real-client test.

**Reasoning:** A flat closed schema is the safest record-level default while VCF Private AI Services behavior is unmeasured. It preserves one planner and one security gate, exposes concrete fields instead of an opaque object, and can reject cross-operation or extraneous fields before adapter dispatch. The record should require real-client tests of both (a) and (b) before implementation freezes the schema. If the client correctly renders and validates every nested branch, I would prefer (a) for its stronger machine-readable contract.

## Q4

**Vote:** (b)

**Interest:** This applies my proposal's own rule that a family without a safe definition readback contract does not implement the operation. Claude's critique specifically challenged me to apply that rule consistently.

**Reasoning:** Identity and shallow metadata cannot detect a report definition's effective content changing behind referenced objects. Shipping with that known blind spot would label identity continuity as revalidation while allowing materially stale intent. Defer both `report:run` and `report:publish`; publishing is not a safer subset and has the wider tenant-visible effect. I would change to (a) if read-only evidence identifies a stable content or revision projection that binds the effective runnable definition.

## Objections

None.
