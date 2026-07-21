# Codex worker, round 1 ballot

## Ballot 1: skills content model

**Vote: Option A.** A client should be able to cite the immutable skill version
and digest it acted on. Tool-call audit records alone identify the invocation,
not the operational guidance that shaped it. Hot-reloading mutable content from
a volume would let filesystem compromise alter trusted instructions outside the
reviewed image, reopening the prompt-injection path Option A closes. Mining can
produce proposed versions quickly without making unreviewed content live.

**Interest:** I proposed Option A and am a party to this fork.

## Ballot 2: credential keyring co-location

**Vote: Option A for v1, with enforced separation.** Put the keyring and
ciphertext on distinct mounts with distinct ownership and exclude the keyring
from database backups. The decision record must say plainly that this protects
against a database-only disclosure, not compromise of the running container or
both mounts. Option B's stronger volume-loss protection is not worth making an
unattended appliance unable to restart without an operator supplying a secret.

Scott must approve this choice because the constitution reserves the
credential-store encryption design as a round-1 architecture decision. The
team can recommend the tradeoff, but should not accept its residual risk for
him.

**Interest:** I proposed the versioned keyring design and am a party to this
fork.
