# 005: skills content model, immutable versioned files in the image

- **Status:** accepted
- **Date:** 2026-07-20
- **Assignment:** vcf-ops-mcp round 1, architecture forks 1-6
- **Orchestrator run:** `orchestrator-run-20260720-231633`
- **Lane:** full protocol
- **Workers dispatched:** claude-worker, codex-worker, agy-worker

## Context

Fork 5. Operational skills content must be exposed two ways: as MCP resources
and prompts for full clients, and via `list_skills`/`get_skill` tools for
tool-calling-only consumers such as VCF Private AI Services. The question is
how the markdown is versioned and how the Phase 3 mining round adds to it.

## Proposals (phase 1, blind)

| Worker | Branch | Proposal commit SHA |
| --- | --- | --- |
| claude-worker | `claude/round1-architecture` | `85cf71244b042709972e8fce4240b3b916965147` |
| codex-worker | `codex/round1-architecture` | `86b3404056be6f67337294dd47bedb477df6a84b` |
| agy-worker | `agy/round1-architecture` | `68e30bdec4329cdb65af5a278ed3388675ba6046` |

**claude-worker:** `skills/<slug>/SKILL.md` with YAML frontmatter carrying
semver, a build-time index, one loader feeding resources, prompts, and tools.
**codex-worker:** immutable `skills/<slug>/<semver>/SKILL.md`, a checked-in
`skills/index.yaml` with content SHA-256 digests, a `current` alias, one
canonical renderer for all four exposures. **agy-worker:** flat markdown in
`skills/`, discovered on boot, with Phase 3 mining committing new files.

## Critique (phase 2, adversarial)

**codex-worker on claude-worker (6):** git history plus one mutable
`skills/<slug>/SKILL.md` gives clients no stable address for the exact content
they used. The frontmatter semver can be overwritten while the same
`skill://<slug>` URI returns different bytes. The build-generated committed
index also has two sources of truth and predictable drift.

**claude-worker on agy-worker (A7):** no slug validation is specified, so
`get_skill("../../../data/creds.db")` is the obvious first thing an adversarial
client tries, and the credential store lives on a mounted volume in the same
container. claude-worker also conceded codex-worker's model beats its own:
"Codex's immutable `<slug>/<semver>/` with a checked-in digest index is better
and I concede it is better than my own fork 5 framing too."

**codex-worker on agy-worker (5):** boot-time discovery of arbitrary markdown
gives no schema validation, path boundary, size limit, provenance, digest,
immutable version, or guarantee that resources, prompts, and tools render the
same content. At 30 skills an unbounded list also wastes context.

**agy-worker on codex-worker:** immutable semver directories plus a central
`index.yaml` add repository churn and conflict-resolution friction for Phase 3,
where an LLM agent generates skills, and forcing a container rebuild for every
skill fix strangles iteration velocity.

## Ballot 1

Four ballots, **4-0 for Option A** (immutable versioned, validated index,
in-image content). No 2-2 split, so the critic seat was not invoked.

| Ballot | Vote | Interest |
| --- | --- | --- |
| orchestrator | A | none |
| claude-worker | A, with a bounded amendment | party; had already conceded in critique |
| codex-worker | A | party; proposed A |
| agy-worker | A | party; proposed B, and switched |

agy-worker's switch is worth recording in its own words, because it conceded
the security argument against its own proposal:

> I concede Option B's hot-reload introduces a prompt-injection vector via the
> volume. [...] without versioned, immutable skills, the audit trail cannot
> definitively reconstruct what instructions the client received.

## Decision (phase 3, synthesis)

**Immutable `skills/<slug>/<semver>/SKILL.md`.** Releases never edit an
existing version; they add a version and advance a `current` pointer. A
checked-in `skills/index.yaml` carries slug, version, title, summary,
maturity, source provenance, and content SHA-256.

**Two independent reasons carried the ballot**, and both belong in the record:

1. **Audit reconstructability.** This repo audits every tool call. A
   `get_skill` result that is "whatever bytes were on the volume at that
   moment" produces an audit record that cannot be replayed, so six months
   later nobody can say what content the client acted on. Immutable versions
   plus digests make the skills read path as reconstructable as every other
   audited path.
2. **Prompt injection.** Skills are prompt content fed to a model that then
   calls actions against infrastructure. In-image content passed review and
   arrived through a build. Volume hot-reload moves that text to a mutable
   surface no reviewer gates, in the same container as the credential store.
   claude-worker's framing: anyone who can write that volume can steer tool
   selection, "a strictly larger blast radius than the `../../../data/creds.db`
   path traversal I flagged in A7."

**One canonical renderer, four exposures.** Resources at
`skill://<slug>/<version>` plus a `current` alias, prompts named `use_<slug>`
that point at the canonical resource, and fixed `list_skills`/`get_skill`
tools. All four render from one immutable catalog object loaded and validated
at startup. Prompts must not maintain a second copy of the content.

**`get_skill` serves only from the validated in-memory index**, never from an
arbitrary path. This closes A7 explicitly. `list_skills` returns metadata-only
filtered listings, not unbounded content.

**A repository validator** enforces safe slugs, valid semver, unique `current`
entries, existing files, digest agreement, bounded file size, required
provenance, and no secrets or lab-specific configuration.

**The index is generated in CI and its exact regeneration validated**, which
answers codex-worker's own two-sources-of-truth objection to claude-worker's
build-time index. A stale committed index is never trusted at runtime. This
also disposes of agy-worker's churn objection: merge friction on a generated
file is a tooling problem, not an architecture one.

**claude-worker's amendment is adopted:** an explicit `SKILLS_DEV_PATH`
overlay, **off by default**, and **refused whenever any registered target is
action-enabled**. Phase 3 mining iterates locally against that overlay;
promotion to servable content is a reviewed commit and an image build. This
gives agy-worker's velocity concern a real answer without putting an
unreviewed prompt source in front of a live target. The refusal condition is
load-bearing and is not an operator preference.

**Phase 3 mining adds candidates through ordinary reviewed commits** with
provenance to source repo path and revision, a portability and secret scan,
and a human-edited distillation. The server must never mount or scrape the
knowledge repositories at runtime. Seed skills use the same process now, so
Phase 3 scales the catalog rather than redesigning it.

**Known limitation, accepted knowingly.** Per 002 the server runs stateless
HTTP, which forgoes `resources/list_changed` and subscriptions. A client
therefore is not notified when `current` advances. claude-worker's C7 flagged
that forks 2 and 5 quietly disagreed on this; the disagreement is resolved by
naming it rather than by changing either fork.

## Division of labor

| Piece | Assigned to | Why this harness |
| --- | --- | --- |
| Skill catalog schema, `index.yaml`, CI generation and exact-regeneration check, repository validator | codex-worker | It designed the immutable layout and the validator's rule set, and both peers conceded its model |
| One canonical renderer feeding resources, prompts, and both tools | claude-worker | Its phase-1 proposal already centered on a single loader feeding all exposures, which is the part of its proposal that survived |
| `SKILLS_DEV_PATH` overlay and its action-enabled refusal | claude-worker | It proposed the amendment and identified the injection boundary the refusal enforces |

agy-worker receives no slice of this fork, having proposed the losing option
and conceded it. It holds slices in 001 and 006.

## Dissent

None standing. agy-worker's Option B lost 4-0 and agy-worker voted against its
own proposal, conceding the prompt-injection and audit-reconstructability
arguments. Its velocity objection was not dismissed: it is answered by the
`SKILLS_DEV_PATH` amendment and by CI-generating the index.

## Protected paths touched

src/vcf_ops_mcp/

## Sign-offs

    Signed-off-by: claude-worker <claude@team.local> 2026-07-20T23:38:12Z
    Signed-off-by: codex-worker <codex@team.local> 2026-07-20T23:33:21Z
    Signed-off-by: agy-worker <agy@team.local> 2026-07-20T23:34:00Z

Transcribed by the orchestrator from each worker's own signature artifact,
because the records live on a branch the workers do not write to. The
artifacts are authoritative and independently checkable:

| Signer | Signature artifact | Commit |
| --- | --- | --- |
| claude-worker | `.team/signoffs/claude-worker-round1-records.md` | `4cde29b` |
| codex-worker | `.team/signoffs/codex-worker-round1-records.md` | `dd9cf51` |
| agy-worker | `.team/signoffs/agy-worker-round1-records.md` | `9576887` |

Each signer confirmed in its artifact that its own dissent, where it has one,
is quoted accurately and was not softened or truncated.
