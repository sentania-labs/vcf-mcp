# TLDR

Round 3 is unblocked and the team has agreed on how to build Phase 1. First
thing I did was re-check the permissions fix live instead of taking it on
faith: the service account now sees **517 objects across 21 adapter kinds**, up
from 4, so Gate 1 will actually demonstrate something. The plan is the read-only
MCP server you specced, built as three parallel slices (codex on the store and
the dispatcher, claude on the VCF client and the read tools, agy on the admin
UI, container, and deploy), roughly **15 to 21 worker-days across 6 to 8
rounds**. Nobody has written a line of code yet, on purpose.

Four things I want your call on rather than mine:

- **Reports is nearly empty in Phase 1 and I want to cut it back.** Report *run*
  is a Phase 2 mutation, and DEVEL has zero completed reports, so what's left is
  a list tool that returns nothing and a download tool with nothing to download.
  I'd ship report **definitions** listing only and let the rest land in Phase 2
  with the run path. That's a reduction against the SPEC's "reports:
  list/run/download" line, which is why I'm asking rather than deciding.
- **DEVEL's cert is self-signed, so we'd ship with TLS verification off for that
  target.** That's honest but it does expose the credentials to anyone on that
  network segment. The clean fix is mounting the lab CA into the container,
  which is deployment trust material and therefore yours. Fine either way, I
  just don't want "verification off" to become permanent by never being asked.
- **A reading of your audit invariant that I want on the record.** "No tool path
  ships without its audit write" is satisfied by writing the audit record
  *before* the call runs. If the *closing* record then fails because the disk
  died mid-call, we return a typed "outcome unknown", hand back the data, refuse
  all further calls, and reconcile later. No software can promise a durable
  write to dead media, so I don't think this weakens anything, but it's your
  invariant and you should get to say so.
- **One decision went 2-2 and the outside critic overruled me.** Who owns the
  skills surface. I voted with claude-worker; cursor sided with codex and agy,
  and I took its side rather than pulling rank. Flagging it because the whole
  point of that seat is that you can see when it fires.

Commenting `approved` starts the actual build: the two day-one spikes, then
`contracts.py`, then three doers building in parallel toward a deployed
container you connect Claude Code to for Gate 1.
