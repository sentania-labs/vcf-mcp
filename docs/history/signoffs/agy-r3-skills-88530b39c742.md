---
reviewed_branch: agy/r3-skills
reviewed_sha: 88530b39c74270a29f7757619a182e1fb7963f9e
reviewed_by: claude-worker
authored_by: agy-worker
timestamp: 2026-07-26T01:04:33Z
tests_run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
result: changes-requested
---

# Peer re-review, skills slice, `agy/r3-skills` at `88530b3`

Re-review of the three blocking items from
`.team/signoffs/agy-r3-skills-41909bb8da77.md`, which stands unedited as the
record of the previous round. Reviewed read-only in the author's worktree
`/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-agy2`; nothing was
changed there and `git status --porcelain --untracked-files=no` is empty at the
end of this review. All experiments ran against `git archive 88530b3` exports
under `/tmp`, never in the author's tree.

`result: changes-requested`, on one half of one item. Items 1 and 3 are closed
with teeth. Item 2 is **partially closed**: the sort itself is correct and I
proved it, but the test that is supposed to keep it from regressing cannot
detect its removal. That is the same "green for the wrong reason" pathology the
requirement existed to prevent, so I am holding on it. It is a few lines to fix.

## Tests

Author's worktree, whole suite:

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q
...............                                                          [100%]
15 passed in 0.36s
```

Skills file alone, verbose, to confirm nothing is skipped or deselected:

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q -v tests/test_skills.py
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
collected 8 items

tests/test_skills.py ........                                            [100%]

============================== 8 passed in 0.32s ===============================
```

10 to 15 as reported. No skips.

## Blocking item 1, placeholder distinguishable structurally. CLOSED

The author took my first option: a `"maturity": "placeholder"` value that
`load_catalog` honors by skipping the entry (`skills.py:168`), plus a guard on
the `current` loop in `get_resource_uris` (`skills.py:63`) so the `/current`
alias does not leak an entry whose skill was dropped. `get_prompts` already had
the equivalent guard. The summary no longer asserts the skill delivers an auth
flow: `"Placeholder for future suite-api auth flow."` in both
`skills/index.json` and the on-disk `metadata.json`, consistent.

I exercised every render path against the real catalog rather than reading the
guards:

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -c "... load_catalog(Path('skills')) ..."
list_skills slugs      : ['actions-how-to', 'metrics-query-patterns']
resource uris          : ['skill://actions-how-to/1.0.0', 'skill://metrics-query-patterns/1.0.0',
                          'skill://actions-how-to/current', 'skill://metrics-query-patterns/current']
prompts                : ['use_actions-how-to', 'use_metrics-query-patterns']
get_skill(current)     : None
get_skill(slug,1.0.0)  : None
read_resource /current : None
read_resource /1.0.0   : None
read_prompt use_...    : None

non-placeholder still renders:
  get_skill(actions-how-to) len: 199
  read_prompt(use_actions-how-to) is not None: True
```

All four render paths refuse the placeholder, the two real skills are
unaffected, and the explicit-version path is closed as well as the `current`
alias. The digest is still verified before the skip (`skills.py:162` runs ahead
of the `continue`), so a placeholder cannot be used as a hole to smuggle
unverified content through.

`test_load_catalog_excludes_placeholder` has teeth. Removing the exclusion:

```
MUTATION: placeholder exclusion removed
FAILED tests/test_skills.py::test_load_catalog_excludes_placeholder
1 failed, 7 passed
```

One forward-facing note for the delivery slice, not blocking and not this
slice's defect. `catalog.current` is a raw field and still carries the
placeholder slug:

```
catalog.current : {'actions-how-to': '1.0.0', 'metrics-query-patterns': '1.0.0',
                   'suite-api-auth-walkthrough': '1.0.0'}
```

Every render path is guarded, so the contract is right. But delivery must
register prompts and resources from `get_prompts()` and `get_resource_uris()`
rather than iterating `catalog.current` itself, or the placeholder reappears at
the MCP boundary. Worth the orchestrator carrying that sentence into the
delivery dispatch.

## Blocking item 2, sorted catalog with a test that holds the guarantee. PARTIALLY CLOSED

The author restructured rather than patching, which is why the file shrank by 61
lines: the whole catalog walk moved into `build_index_data` in `skills.py:176`,
and `tools/generate_skills_index.py` now imports and calls it. That also takes
non-blocking item 6. The sort lives at `skills.py:217`, before the return, so
both the generator and the checker get it from one place.

### The sort itself is correct. Verified, not assumed.

I re-ran the twelve-slug experiment on a fresh `git archive` export, with the
same creation order as last time so readdir scrambles the same way:

```
=== raw iterdir order on this fs ===
['skill-07', 'skill-10', 'skill-06', 'skill-03', 'skill-11', 'skill-02',
 'skill-09', 'skill-01', 'skill-04', 'skill-12', 'skill-05', 'skill-08']

Generated index with 12 skills.

=== generated list order ===
['skill-01', 'skill-02', 'skill-03', 'skill-04', 'skill-05', 'skill-06',
 'skill-07', 'skill-08', 'skill-09', 'skill-10', 'skill-11', 'skill-12']
sorted? True

=== idempotence: regenerate, byte-compare ===
Generated index with 12 skills.
RUN2 byte-identical
```

Readdir order is as scrambled as it was at `41909bb`; the output is now sorted
regardless. The three-skill real tree also regenerates byte-identical to the
committed `skills/index.json` twice running, so a CI step of the shape
"regenerate and `git diff --exit-code`" is now safe:

```
RUN1: byte-identical to committed
RUN2: byte-identical to committed
```

And the checker agrees with the generator on the twelve-slug tree, so the two
have not drifted apart in the refactor:

```
12-slug: checker PASSES on generator output
```

### The test does not hold the guarantee. This is what I am blocking on.

`test_build_index_data_is_sorted` builds a two-entry tree with `z-skill` and
`a-skill` and asserts `[0]` is `a-skill` and `[1]` is `z-skill`. On this
filesystem readdir already returns them in that order, so the assertion passes
whether or not the sort exists. I deleted the sort line and re-ran:

```
MUTATION: catalog.sort removed from build_index_data
........                                                                 [100%]
8 passed in 0.30s
```

Eight of eight still green with the guarantee gone. The reason:

```
$ python3 -c "make z-skill, a-skill under a fresh tmpdir, print iterdir order"
trial 0 ['a-skill', 'z-skill']
trial 1 ['a-skill', 'z-skill']
trial 2 ['a-skill', 'z-skill']
```

The fixture never scrambles, so the test cannot distinguish sorted output from
readdir output. My requirement was the sort "and a test that asserts the
generated list is sorted so the guarantee does not silently regress." The
implementation half is done and proven. The regression guard is not there, and
I have just demonstrated the regression it is meant to catch passing silently.

Two ways to close it; the second is my preference because it does not depend on
what the filesystem happens to do:

- keep the real-tree fixture but build enough slugs that readdir demonstrably
  scrambles (twelve worked for me, above), and assert both
  `slugs == sorted(slugs)` and that the raw `iterdir()` order was *not* already
  sorted, so the test fails loudly if the fixture stops scrambling instead of
  going quietly vacuous
- or take the filesystem out of it: monkeypatch `Path.iterdir` for the duration
  of the test to yield the slug directories in reverse order, then assert the
  output is sorted. Deterministic on any filesystem, and it is the assertion the
  requirement actually wants

Either one must fail when `skills.py:217` is deleted. That is the check to run
before calling it done.

## Blocking item 3, failing-direction test plus a real-tree run. CLOSED

Both halves landed.

`test_check_index_exact_regeneration_tampered` generates a valid index via
`build_index_data`, asserts the check passes, then rewrites `metadata.json` with
a changed title and asserts `pytest.raises(SkillLoadError, match="does not match
metadata on disk")`. That is the failing direction I asked for. It has teeth:

```
MUTATION: expected_index["skills"] != existing_catalog neutered
FAILED tests/test_skills.py::test_check_index_exact_regeneration_tampered
1 failed, 7 passed
```

`test_check_index_exact_regeneration_real_repo` points the check at
`Path(__file__).parent.parent / "skills"`, the repo's real tree. I confirmed the
guard is not silently skipping it and that the check has teeth on the real tree
rather than merely being called:

```
skills/ exists: True -> guard does not skip
real tree: check PASSES as committed
real tree stale: raised -> Skills catalog in index.json does not match metadata on disk.
```

Committed `skills/index.json` is not stale, and staleness is now a suite failure
rather than something only a separate CI step would catch. Item 3 closed.

Small note, not blocking: the `if skills_dir.exists():` wrapper means that if
`skills/` is ever moved or renamed, this test goes green by doing nothing rather
than failing. An `assert skills_dir.exists()` would be strictly better and costs
one line. Mentioning it because it is the same silent-vacuity shape as item 2,
though here the directory does exist so the test is live today.

## Non-blocking items 4 to 6, what was taken

**Item 4, content-side tamper case. TAKEN.**
`test_load_catalog_content_tamper` writes valid content, indexes its correct
digest, then rewrites `SKILL.md` and asserts the load rejects it. That is the
direction the invariant exists for, and it reads as documentation the way I
hoped. Both digest tests have teeth:

```
MUTATION: actual_digest != meta.content_sha256 neutered
FAILED tests/test_skills.py::test_load_catalog_digest_mismatch
FAILED tests/test_skills.py::test_load_catalog_content_tamper
2 failed, 6 passed
```

**Item 5, `ValueError` on non-numeric version components. PARTIALLY TAKEN.**
`skills.py:214` is now
`[int(x) if x.isdigit() else x for x in v.replace('-', '.').split('.')]`. That
fixes the case I named and the numeric ordering is right, but mixing `int` and
`str` in the sort key means a non-numeric component in the *same position* as a
numeric one still raises, just `TypeError` now instead of `ValueError`:

```
['1.0.0', '1.1.0']            -> ['1.0.0', '1.1.0']            current=1.1.0
['1.0.0', '1.10.0', '1.9.0']  -> ['1.0.0', '1.9.0', '1.10.0']  current=1.10.0
['1.0.0', '1.1.0-rc1']        -> ['1.0.0', '1.1.0-rc1']        current=1.1.0-rc1
['1.0.0', '1.0.0-rc1']        -> ['1.0.0', '1.0.0-rc1']        current=1.0.0-rc1
['1.0.0', '1.0.x']            -> TypeError: '<' not supported between instances of 'str' and 'int'
['1.0.0', 'v2']               -> TypeError: '<' not supported between instances of 'str' and 'int'
```

Also note row four: `1.0.0-rc1` now sorts *after* `1.0.0`, so a release
candidate would become `current` over its own release. Semver has it the other
way. Neither is blocking, both are latent until someone ships a second version
of a skill, and a real fix is one small comparable-version helper rather than a
lambda. Worth an issue so it is not rediscovered at the worst moment.

**Item 6, duplicated catalog walk. TAKEN, and well.**
One walk in `build_index_data`, imported by the generator. The drift mode I was
worried about (checker passing while the generator writes something else) is
gone by construction, and I confirmed agreement empirically on the twelve-slug
tree. Two cosmetic leftovers from the extraction, neither blocking: the
generator still imports `hashlib` and `os`, both now unused (`re` is correctly
gone), and it reaches `src` via `sys.path.insert`, which is fine until delivery
lands packaging and then becomes redundant.

## Nothing previously confirmed regressed

Checked against `88530b3` rather than from memory.

**Claim 1, four render paths agree.** Still true, and the placeholder guards did
not introduce an asymmetry: `read_resource` and `read_prompt` both still return
`skill.content`, the same string `get_skill` returns. Confirmed above that a
non-placeholder skill renders identically on every path.

**Claim 2, digest verification.** Still enforced on every load, now with both
tamper directions covered. Mutation-tested above.

**Claim 5, the critic's binding rider.** Intact. `skills.py` imports stdlib only
(`hashlib`, `json`, `logging`, `dataclasses`, `pathlib`, `typing`), and the only
inbound reference to skills anywhere in `src` outside `skills.py` is still

```
88530b3:src/vcf_ops_mcp/contracts.py:30:    READ_SKILLS = "read:skills"
```

a scope-string constant, not a dependency. The new `sys.path` hack points the
*generator* at `src`, which is a tools-to-src direction and does not create a
Gate 1 dependency on this slice. The slice can still be held back.

**Claim 6, no lab material.** Re-read all three `SKILL.md` bodies at this SHA.
Unchanged from `41909bb`; the only content-adjacent edit is the placeholder's
summary string. No FQDN, hostname, username, password, API key, token, session
material, IP address, or `vcf-lab-*` identifier. A pattern grep over the diff
returns nothing:

```
$ git diff 41909bb 88530b3 | grep -nEi '\+.*(password|passwd|api[_-]?key|secret|token|vcf-lab|sentania\.net|Bearer |[0-9]{1,3}(\.[0-9]{1,3}){3})'
none
```

Fixtures remain synthetic `tmp_path` trees.

**Em-dashes and en-dashes.** Clean in the added lines:

```
$ git diff 41909bb 88530b3 | grep -nP '^\+.*[\x{2014}\x{2013}]'
none (exit 1)
```

**Scope.** Five files, all inside what `docs/proposals/2/WORKPLAN.md:127` names
for this slice. `src/vcf_ops_mcp/contracts.py` is not touched. The protected
`src/vcf_ops_mcp/` path is authorized by
`docs/decisions/009-phase1-build-synthesis.md`, signed by all three doers.

**Still true, still not this slice's.** Bare `python3 -m pytest -q` without
`PYTHONPATH=src` fails collection for both `test_contracts.py` and
`test_skills.py`; there is no `pyproject.toml`, `conftest.py`, or `pytest.ini` at
this SHA. Packaging is the delivery slice's. Repeating it so the round does not
find it at CI time.

## Summary for the author

One thing left, and it is the test half of item 2 only. Make
`test_build_index_data_is_sorted` fail when `skills.py:217` is deleted, by either
scrambling the fixture demonstrably or monkeypatching `iterdir` to reverse.
Verify by actually deleting the sort line and watching the test go red before you
put it back.

Everything else is closed. Item 1 is closed cleanly and the way I hoped, item 3
is closed with both halves and real teeth, item 4 is taken, item 6 is taken and
the extraction is better than the patch I asked for. Item 5 is improved but has
a residue worth an issue rather than a fix in this slice.

Re-review at the new SHA.

Co-authored-by: claude-worker <claude@team.local>
