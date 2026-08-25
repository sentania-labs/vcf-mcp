# Issue #4, the short version

The three-line permissions fix is right and we will ship it. But it is not
"the only thing between merged code and a running service," and the team found
that from read-only recon rather than by guessing: there are four more defects
in the path, and two of them are in the app, not the workflow. The biggest one
is that `/healthz` returns 503 by construction at every possible image digest,
so the second acceptance criterion on the issue cannot be met by any change to
a CI file. The plan is to fix the whole CI path now (Slice A), prove the image
push on the round branch before it ever touches `main`, and file the app work
as a separate slice (Slice B).

## What we need from you

- **Split the issue, or not?** Slice A gets you a green Build & Deploy run.
  Slice B is what gets you a 200 from `/healthz`, and it is a day or two of
  real work because it needs a durable audit store that does not exist yet.
  We recommend closing #4 on Slice A and filing Slice B as its own issue. The
  alternative is #4 stays open for days.
- **Three Actions secrets the workflow reads do not exist.** Only
  `DOCKER_DEPLOY_KEY` is there. We need you to confirm that key is actually
  the `vcf-mcp` slot's key, and to create `DOCKER_DEPLOY_HOST` and
  `SERVICE_URL` as repository *variables* (they are lab hostnames, not
  credentials). We will tell you the exact value shape; hearthgate's
  convention and this workflow's convention disagree and one of them will
  silently produce `deploy@deploy@host`.
- **What can the deploy key actually run?** Our workflow calls
  `vcf-mcp get-digest` over ssh. That verb appears nowhere outside our own
  file. hearthgate's key on the same host runs arbitrary `scp` and
  `docker compose`, which is a general shell key, not a forced command. If ours
  is the hearthgate shape, the deploy step needs rewriting around a compose
  file and Slice A roughly doubles. One read-only question to lab-admin settles
  it, and we would rather ask than find out on `main`.
- **OK to push images to GHCR from `round/*` branches?** This is what buys us a
  test loop instead of one blind shot per merge. The package is private and
  tagged per commit, and hearthgate already does exactly this. Cost: the
  registry accumulates images built from code that has not passed external
  review. Veto is free, the fallback is just today's behavior plus the fix.

## What `approved` kicks off

A build round: the workflow slice gets written, peer-reviewed, and merged, and
the first green push to GHCR gets proven on the round branch before anything
touches `main`. We come back with the run link and the healthz output as
evidence, including if healthz is still 503 because you deferred Slice B.
