# claude-worker, round 1 ballot

Phase 3. I read all three critiques read-only via `git show` before voting.
I am an interested party on ballot 2 (it is my own C3) and I state that
below.

## Ballot 1: skills content model (fork 5)

**Vote: A**, with one bounded amendment.

Interest: I proposed a mutable `skills/<slug>/SKILL.md` in phase 1 and
already conceded codex's immutable versioned layout in my critique (A7).
This vote is consistent with that concession, not new ground.

Reasoning. On the audit question, yes, and it is decisive. The constitution
requires every tool call to record key identity, target, tool, an args
digest, and result status. A `get_skill` call whose result is "whatever
bytes were on the volume at that moment" produces an audit record that
cannot be replayed: six months later nobody can say what content the client
actually acted on. Option B has no version and no digest, so the audit entry
for a skills read is not reconstructable. That is not a style preference, it
is the audit invariant applied to a tool path that agy's model leaves
unaddressed.

On injection, also yes. In-image content is content that passed review and
arrived through a signed build. Volume hot-reload moves skill text to a
mutable surface that no reviewer gates, and skills are prompt content fed to
a model that then calls actions against infrastructure. Anyone who can write
that volume can steer tool selection. That is a strictly larger blast radius
than the `../../../data/creds.db` path traversal I flagged in A7, and it
lands in the same container as the credential store.

Agy's velocity concern is real but it is a Phase 3 problem being solved in a
Phase 1 decision. The amendment that resolves it: an explicit
`SKILLS_DEV_PATH` overlay, off by default, refused whenever any registered
target is action-enabled, and never set on the lab appliance. Phase 3 mining
iterates locally against that overlay, and promotion to a skill anyone can
serve is a reviewed commit and an image build. That gives agy the iteration
loop without putting an unreviewed prompt source in front of a live target.

The index-churn objection I do not credit. If a generated `index.yaml` is
painful for an agent to edit, generate it in CI and validate exact
regeneration, which codex already proposed in its own C6 against me. Merge
friction on a generated file is a tooling problem, not an architecture one.

## Ballot 2: credential keyring co-location (fork 3)

**Vote: A**, and this is the team's call, not Scott's.

Interest: C3 is mine. I raised the co-location objection and I am voting
against the stronger of my own two proposed remedies. My original wording
was "pick one and say which, because the difference is the entire threat
model," and I still hold the second clause. The complaint was that codex
presented encryption at rest as load-bearing without naming what it bears.
Honest documentation answers that complaint. It does not require B.

Reasoning. B's cost is disqualifying for this deployment. An unattended lab
appliance behind fleet-caddy has to survive a host reboot, a docker daemon
restart, and an image redeploy without a human present. B means every one of
those ends in a container that is up, healthy to the orchestrator, and
serving nothing until Scott types a passphrase. The predictable operator
response to that is to put the passphrase in an env var in the compose file
on the same host, which restores exactly the co-location we were trying to
escape while adding a boot dependency and the process-environment exposure
class codex correctly attacked in my fork 4. A control that degrades into
the thing it replaced, plus a new outage mode, is worse than the honest
version of A.

What A must say, and the record is not acceptable without it: the threat
encryption at rest actually closes here is a database file copied without
its filesystem context (a backup blob, a volume snapshot mounted elsewhere,
an errant `docker cp` of the data volume). It does not defend against an
attacker with read access to the container filesystem or the host. Separation
is enforced by a distinct mount for the keyring, distinct ownership and mode
checked at startup with a fail-closed refusal, and explicit exclusion of the
keyring volume from the same backup artifact as the database. If those three
are not implemented, the encryption claim should be struck from the record
rather than softened.

Why this is not Scott's. The constitution routes to the principal anything
that "widens the action blast radius or weakens an invariant." A does neither.
There is no invariant requiring key/ciphertext separation, and the credential
store is already an escalated round-1 decision record under Pinned tooling
per the orchestrator's ruling 1. Scott sees this threat model when he
approves that record, which is the right place for him to overrule it if the
lab warrants more. Escalating it separately asks him the same question twice.

Co-authored-by: Claude <claude@team.local>
