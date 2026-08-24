---
reviewed_branch: agy/r3-skills
reviewed_sha: 41909bb8da77a97a1ada47301f45ab3379cbe3b0
reviewed_by: claude-worker
authored_by: agy-worker
timestamp: 2026-07-26T00:48:26Z
tests_run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
result: changes-requested
---

# Peer review, skills slice, `agy/r3-skills` at `41909bb`

Reviewed read-only in the author's worktree
`/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-agy2`. Nothing was
changed there. Determinism experiments were run against a `git archive` export
in `/tmp`, not in the author's tree.

`result: changes-requested`. Claims 3, 4, and 7 are denied. The module code is
in good shape and I found no correctness bug in it; the three denials are a
missing negative test, a placeholder that ships as if it were finished content,
and a non-deterministic index generator that will make the CI check flaky as
soon as a fourth skill lands. All three are cheap to fix.

## Tests

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
..........                                                               [100%]
10 passed in 0.32s
```

Note, not a defect of this slice: bare `python3 -m pytest -q` fails collection
with `ModuleNotFoundError: No module named 'vcf_ops_mcp'` for both
`test_contracts.py` and `test_skills.py`, because the repo has no `pyproject.toml`,
no `conftest.py`, and no `pytest.ini` at this SHA. Packaging belongs to the
delivery slice, and `test_contracts.py` has the same problem, so this predates
`agy/r3-skills`. Flagging it for the orchestrator so the round does not discover
it at CI time.

## Claim by claim

### 1. All four render paths exist and agree. CONFIRMED

`src/vcf_ops_mcp/skills.py` carries all four on `SkillCatalog`:

- resources, `get_resource_uris` (line 57) and `read_resource` (line 66)
- prompts, `get_prompts` (line 80) and `read_prompt` (line 92)
- `list_skills` (line 40)
- `get_skill` (line 32)

`read_resource` and `read_prompt` both return `skill.content`, the identical
string `get_skill(...).content` returns. There is no reduced variant. I ran the
real catalog to confirm a tools-only client loses no content:

```
$ PYTHONPATH=src python3 -c "... load_catalog(Path('skills')) ..."
{'slug': 'actions-how-to', 'version': '1.0.0', 'title': 'Actions How-to', 'summary': 'How to execute VCF Ops actions with plan-then-apply.', 'maturity': 'seed', 'is_current': True}
{'slug': 'metrics-query-patterns', 'version': '1.0.0', ...}
{'slug': 'suite-api-auth-walkthrough', 'version': '1.0.0', ...}
```

`get_skill` reaches every `(slug, version)` pair plus the `current` alias, same
coverage as the resource path. Two asymmetries I checked and accept:

- Prompts cover only `current` versions, resources and `get_skill` cover every
  version. That is the conventional shape for prompts and it costs a
  tool-calling client nothing, since tools are the path those clients use.
- `list_skills` omits `source_provenance` and `content_sha256`, which the index
  carries. The resource path exposes neither either, so this is symmetric rather
  than a tools-only loss. Worth adding `source_provenance` later so a client can
  see where content came from, but not blocking.

Scoping note for the record: no MCP binding exists at this SHA. These four are
plain methods with no server registration, because `app.py` and the MCP binding
are the delivery slice's, per `docs/proposals/2/WORKPLAN.md`. That is correct
for this slice, and it is the same fact that makes claim 5 hold. The delivery
slice must actually call all four.

### 2. Digest verification fails on tampered content. CONFIRMED

`tests/test_skills.py:80` `test_load_catalog_digest_mismatch` is a real negative
control: it writes an index whose `content_sha256` is `"bad_digest"` and asserts
`pytest.raises(SkillLoadError, match="Digest mismatch")`. It passes, and the
raise it exercises is `skills.py:159`, the same single comparison
`actual_digest != meta.content_sha256` that a content-side tamper would trip.

One improvement I would like but am not blocking on: the test mutates the
index-side digest rather than the content body. Both directions hit the same
branch so coverage is genuine, but a case that writes valid content, indexes its
correct digest, then appends a line to `SKILL.md` and asserts the load rejects it
is the scenario the invariant actually exists to catch, and it reads better as
documentation.

### 3. `check_index_exact_regeneration` would fail on a stale index. DENIED

The function is correct. The test does not prove it.

`tests/test_skills.py:76` calls `check_index_exact_regeneration(skills_dir)` once,
bare, in the happy path of `test_load_catalog_and_verify`. There is no
`pytest.raises` anywhere for it. The suite proves only that a correct index
passes, which is exactly the direction claim 3 says is not enough.

I verified by hand that the failing direction does work, so this is a test gap
and not a code defect:

```
$ PYTHONPATH=src python3 -c "copy skills/ to tmp, append TAMPERED to actions-how-to SKILL.md, call check_index_exact_regeneration"
caught: Skills catalog in index.json does not match metadata on disk.
```

Second, related gap: nothing in the suite ever points
`check_index_exact_regeneration` at the repo's real `skills/` directory. Every
call is against a `tmp_path` fixture. So if the committed `skills/index.json`
goes stale, the test suite stays green and only a separate CI step would catch
it, and that step is the one claim 7 shows is not yet reliable.

What I need to see to lift this: a test that builds a valid tree, mutates
`SKILL.md` (or `metadata.json`, or drops a version directory), and asserts
`pytest.raises(SkillLoadError)`. Plus one test that runs the check against the
real `skills/` tree so staleness is a suite failure.

### 4. The auth walkthrough is honestly marked as a placeholder. DENIED

It is honest in the commit message and nowhere else. The artifact ships as if it
were finished content.

`skills/suite-api-auth-walkthrough/1.0.0/metadata.json` carries
`"maturity": "seed"`, byte-identical in that field to the two real skills. There
is no `placeholder` maturity, no `draft` flag, no exclusion. `skills/index.json`
lists it as a full catalog entry with a digest, and puts it in `current`
alongside the two complete skills. Running the catalog, a client sees:

```
{'slug': 'suite-api-auth-walkthrough', 'version': '1.0.0', 'title': 'Suite-API Auth Walkthrough', 'summary': 'Auth flow for the suite-api.', 'maturity': 'seed', 'is_current': True}

get_skill('suite-api-auth-walkthrough').content
'# Suite-API Auth Walkthrough\n\n[SLOT: claude-worker auth walkthrough content]\n'

get_prompts() -> {'name': 'use_suite-api-auth-walkthrough', 'description': 'Auth flow for the suite-api.'}
```

So every one of the three checks in claim 4 fails. The catalog counts it as
complete, the index counts it as complete and current, and all four render paths
present it to a client as a usable walkthrough whose body is a build-time slot
marker. A model that calls `use_suite-api-auth-walkthrough` because the summary
promises "Auth flow for the suite-api" gets a bracket token and will improvise
the auth flow from nothing, which for this particular skill means guessing at
credentials. That is worse than the skill not existing.

What I need to see: the placeholder distinguishable structurally, not just in
prose. Any one of these is fine, and the first is my preference because it keeps
the slot visible to the team without exposing it:

- a `"maturity": "placeholder"` value that `load_catalog` honors by excluding the
  entry from `list_skills`, `get_prompts`, and `get_resource_uris`, with
  `get_skill` and `read_resource` returning `None`, plus a test asserting exactly
  that
- or drop the skill from `skills/index.json` and `current` entirely until the
  content lands, keeping the directory on disk as the slot

Either way the summary should stop asserting the skill delivers an auth flow
while its body is empty.

**I owe this content.** Per `docs/proposals/2/WORKPLAN.md:139`, the suite-api
auth walkthrough seed content is authored by claude-worker from its measured
recon and handed over as content, and that does not make me a co-owner of this
slice. Recording the one fact it must carry so it is not lost if I am not the
one who writes it up:

> The local auth source value the suite-api expects is **`LOCAL`**. It is not
> `"Local Users"`, which is only the display label the admin UI picker shows for
> that same source. Sending the display label produces a 401 that is
> indistinguishable from a wrong password, with no hint that the auth source
> field is the problem. This is the most confusing 401 this API produces and the
> walkthrough leads with it.

That fact goes in the content when I hand it over. It is not agy-worker's to
write and its absence here is not a defect of this slice.

### 5. The critic's binding rider is intact. CONFIRMED

Skills is structurally independent of the delivery slice in both directions.

Outbound, `src/vcf_ops_mcp/skills.py` imports stdlib only:

```
1:import hashlib
2:import json
3:import logging
4:from dataclasses import dataclass
5:from pathlib import Path
6:from typing import Mapping
```

No import of `contracts`, no import of anything delivery owns.

Inbound, `git grep -n 'skills' 41909bb -- src` outside `skills.py` returns
exactly one line:

```
41909bb:src/vcf_ops_mcp/contracts.py:30:    READ_SKILLS = "read:skills"
```

That is a scope-string constant in codex-worker's contracts enum. It is a name,
not a dependency: `contracts.py` does not import or call anything in `skills.py`,
and it predates this branch. No Gate 1 path depends on this slice. The rider from
`docs/proposals/2/WORKPLAN.md:132` holds, and this slice can be held back or
redispatched without touching the deploy.

### 6. The seed skills carry no lab material. CONFIRMED

I read all three bodies in full, not just the metadata. Complete content of the
three `SKILL.md` files at this SHA:

- `actions-how-to`: five lines describing plan (dry-run) then apply. Generic
  process description, no target named.
- `metrics-query-patterns`: five lines, `maxSamples=1` for latest data and query
  stat keys before values. Generic API guidance, no target named.
- `suite-api-auth-walkthrough`: three lines, the placeholder in claim 4.

No FQDN, no hostname, no username, no password, no API key, no token, no session
material, no IP address, no lab identifier of any kind. Nothing referencing
`vcf-lab-operations` or `vcf-lab-operations-devel`. A diff-scoped grep for lab
identifiers and credential-shaped strings across the added files returned nothing.

### 7. `tools/generate_skills_index.py` is deterministic. DENIED

Same input does not reliably produce the same output. The `skills` list is
emitted in raw `Path.iterdir()` order and never sorted.

`json.dump(index_data, f, indent=2, sort_keys=True)` at line 76 sorts dictionary
keys, which is why each entry's fields come out alphabetical, but `sort_keys` has
no effect on list element order. The `catalog` list is appended in `iterdir()`
order (line 33) with no sort before the dump. `check_index_exact_regeneration` in
`skills.py` does sort both sides before comparing (line 214), so the library
check is order-tolerant, but a CI step of the shape "regenerate and
`git diff --exit-code`" compares bytes and will fail on a reordering.

Run twice against the real tree, stable, because `iterdir()` order does not
change for an unchanged directory:

```
$ python3 tools/generate_skills_index.py   # against a git archive export in /tmp
Generated index with 3 skills.
RUN1: matches committed
Generated index with 3 skills.
RUN2: identical to RUN1
```

That is the check passing for the wrong reason. ext4 with `dir_index` returns
entries in a hash order of the filename, which for these three particular slugs
happens to come out alphabetical. It is not a guarantee and it does not survive
more entries. Twelve slugs on the same filesystem:

```
$ python3 -c "print([p.name for p in Path('/tmp/ordercheck2/skills').iterdir()])"
['skill-07', 'skill-10', 'skill-06', 'skill-03', 'skill-11', 'skill-02', 'skill-09', 'skill-01', 'skill-04', 'skill-12', 'skill-05', 'skill-08']

$ python3 tools/generate_skills_index.py
Generated index with 12 skills.

$ python3 -c "order = [s['slug'] for s in json.load(open(index))['skills']]; print(order); print('sorted?', order == sorted(order))"
['skill-07', 'skill-10', 'skill-06', 'skill-03', 'skill-11', 'skill-02', 'skill-09', 'skill-01', 'skill-04', 'skill-12', 'skill-05', 'skill-08']
sorted? False
```

The generated order is exactly readdir order. So the CI check is one skill away
from failing spuriously, and it will fail differently on a different filesystem
or a fresh checkout even with today's three skills.

What I need to see: `catalog.sort(key=lambda e: (e["slug"], e["version"]))`
immediately before building `index_data`, and a test that asserts the generated
list is sorted so the guarantee does not silently regress. No timestamps and no
absolute paths are baked into the index, which I did check and which is correct
as written.

Two smaller things in the same file, neither blocking:

- `versions.sort(key=lambda v: [int(x) for x in v.split('.')])` at line 68 raises
  `ValueError` on any non-numeric version component, so the first `1.1.0-rc1`
  crashes the generator rather than reporting a bad version. Same expression is
  duplicated in `skills.py:211`.
- That version-sort and the whole catalog walk are duplicated between
  `tools/generate_skills_index.py` and `check_index_exact_regeneration`. Two
  copies of the rule are two chances for them to drift, and the drift mode is
  the check passing while the generator writes something else. Worth having the
  check import the generator's walk, or the reverse.

## Baseline checks

**Em-dashes and en-dashes.** Clean in this diff. Scoped to added lines, since a
tree-wide grep at this SHA hits a pre-existing ballot file that is not this
slice's:

```
$ git diff 33bca5d..41909bb | grep -nP '^\+.*[\x{2014}\x{2013}]'
dash-in-diff exit=1
```

Exit 1 is no match, which is the pass. For the record, the tree-wide grep does
hit `docs/proposals/2/ballots/critic-r3-skills-ownership-vote.md:8`, which is a
round-3 ballot document that predates this branch and is untouched by this diff.
The orchestrator may want that cleaned up separately; it is not agy-worker's.

**Credentials and lab identifiers.** None. See claim 6. Fixtures are synthetic
`tmp_path` trees built inside the tests, and no captured appliance output is
committed.

**Protected path.** The diff touches `src/vcf_ops_mcp/skills.py`, inside the
protected `src/vcf_ops_mcp/` path, authorized by
`docs/decisions/009-phase1-build-synthesis.md` and signed by all three doers.
The file list stays inside what `docs/proposals/2/WORKPLAN.md:127` names for this
slice: catalog load, digest verification, index regeneration check, four render
paths, three seed skills. Nothing outside that appears.

**Scope honesty.** `src/vcf_ops_mcp/contracts.py` is not touched:

```
$ git diff --name-only 33bca5d..41909bb | grep contracts
grep exit=1
```

Correct, that file is codex-worker's alone. All 10 changed files are new and all
belong to this slice.

The one scope-honesty failure is claim 4. The commit message says "a placeholder
for the suite-api auth walkthrough content," which is honest, but the artifact
itself is indistinguishable from finished work in the catalog, the index, and all
four render paths. That is precisely the "remaining item quietly half-present in
a shape a later reader would mistake for finished" case. A reader six weeks from
now looking at `skills/index.json` sees three complete seed skills.

## Summary for the author

Blocking:

1. Claim 4. Mark the auth walkthrough placeholder structurally so the catalog,
   the index, and all four render paths stop presenting it as a finished skill.
2. Claim 7. Sort the catalog list in `tools/generate_skills_index.py` before the
   dump, and test that it stays sorted.
3. Claim 3. Add a negative test for `check_index_exact_regeneration`, and run it
   against the real `skills/` tree.

Not blocking, worth doing while you are in here:

4. A content-side tamper case for the digest test, alongside the existing
   index-side one.
5. The version-sort `ValueError` on non-numeric version components.
6. The duplicated catalog walk between the generator and the checker.

Everything else I was asked to check passed, and the module itself reads well:
frozen slotted dataclasses, the digest check on every load, and the
`SKILLS_DEV_PATH` overlay correctly refusing when any target is actions-enabled
(`skills.py:118`, tested at `tests/test_skills.py:139`). That last one is a
genuinely good instinct that nobody asked me to check and I want it noted.

Re-review at the new SHA once the three blocking items land.

Co-authored-by: claude-worker <claude@team.local>
