# Round 4 ballot, agy-worker

## Question A: split the deploy job into build and deploy?

**Vote: For**

Splitting the job and running the build phase on round branches drastically improves our feedback loop. It verifies our permissions fix and image creation before merging to `main`, exactly matching the pattern in the sibling repository we are copying. While publishing images from unreviewed code has a policy cost, the value of proving the workflow structure outstrips it in this case. The round-branch publication should be filed as a numbered decision for Scott to review; if he vetoes it, our fallback is to restrict the push to `main` and leave the build-only step running on round branches.

## Question B: rename ai-log-depot.yml to vcf-ops-mcp.yml this round?

**Vote: For**

Leaving an inaccurate filename actively misleads future residents and will only get harder to change once status checks are enforced. Performing the rename as a standalone `git mv` in its own commit before the substantive workflow changes completely neutralizes the history fragmentation objection, as the diffs remain cleanly separated. This vote is independent of Question A, as correcting the file identity holds value regardless of how the jobs inside it are structured.
