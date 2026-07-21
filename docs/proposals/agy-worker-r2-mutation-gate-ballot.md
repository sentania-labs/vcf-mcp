# Antigravity worker, round 2 mutation gate ballot

- **Branch:** `agy/r2-mutation-gate`
- **Timestamp:** 2026-07-21T17:39:07Z
- **Protocol:** phase 3 ballots

## Q1
**Vote:** b
**Interest:** I proposed supporting batch alerts and criticized the one-alert cap. I am voting for the option that implements batch support safely.
**Reasoning:** Operators manage alert storms in batches. A hard cap of one destroys the primary workflow. A bounded batch with per-alert outcomes natively leverages the array returned by the API, serving the operator's intent while keeping revalidation time predictably within the apply deadline.

## Q2
**Vote:** c
**Interest:** I proposed (b) in my critique after discovering populate drift and the lack of a validate endpoint. I am voting against my own earlier position.
**Reasoning:** This round was convened specifically to close the stale plan vulnerability. Accepting the TOCTOU gap under option (b) leaves the vulnerability open for the most destructive capability family. Since actions are ungrantable until Phase 2 anyway, the cost of option (c) is zero for the MVP. We must block action apply until we can prove populate is safe or find another valid revalidation source.

## Q3
**Vote:** b
**Interest:** I initially proposed a nested object which Claude correctly identified as the worst shape for clients struggling with unions. I am voting for Claude's flattening proposal.
**Reasoning:** Since nobody has tested the discriminated union against VCF Private AI Services, we cannot confidently ship it. Flat optional scalars with server side rejection of unrelated fields are the most reliable shape for limited LLM clients. It avoids both the client rendering risks of a union and the gate duplication of typed planners.

## Q4
**Vote:** a for `report:run`, b for `report:publish`
**Interest:** none
**Reasoning:** Generating a report without publishing it (`report:run`) is essentially a heavy read with a stored result; the blast radius of executing a shallowly verified definition is low, so shipping it with a documented limitation is acceptable. `report:publish` has tenant visible side effects, so the inability to verify the exact definition content before apply makes it unsafe. We should defer `report:publish` until a deep readback is available.

## Objections
none
