---
reviewed_branch: agy/r3-skills
reviewed_sha: 6ffe808d96635943fe3c56c69a05458749efe68d
reviewed_by: claude-worker
authored_by: agy-worker
timestamp: 2026-07-26T01:22:20Z
tests_run: PYTHONPATH=src python3 -m pytest -q
result: signed-off
---

# Peer re-review, skills slice, `agy/r3-skills` at `6ffe808`

Third and final review pass. The prior two markers stand unedited as the record
of their rounds: `agy-r3-skills-41909bb8da77.md` (initial) and
`agy-r3-skills-88530b39c742.md` (`changes-requested` on the test half of item 2).

`result: signed-off`. The one item I held on is closed, with teeth I verified by
running the regression it was supposed to catch. Nothing regressed.

Head resolved myself rather than taken on report:

```
$ git rev-parse agy/r3-skills
6ffe808d96635943fe3c56c69a05458749efe68d
```

Reviewed read-only in the author's worktree
`/home/scott/foundry/projects/.worktrees/vcf-ops-mcp-r1-agy2`; nothing was
changed there and `git status --porcelain --untracked-files=no` is empty at both
the start and the end of this review. Every mutation experiment ran against a
`git archive 6ffe808` export under `/tmp/claude-rev-skills`, never in the
author's tree. I re-ran all named claims rather than accepting the orchestrator's
pre-dispatch results.

Scope note: items 1 and 3 are closed and were not reopened. The `catalog.current`
placeholder-slug observation is a forward-facing item for the delivery slice,
already recorded, and is not held against this slice. I confirmed it is still
exactly as previously described and nothing more (bottom of this marker).

## Claim 1, the mutation now fails. CONFIRMED

This was the whole point of the hold. I deleted the sort at `skills.py:217` from
the scratch export and ran the file:

```
$ (delete `catalog.sort(key=lambda x: (x["slug"], x["version"]))` from build_index_data)
$ PYTHONPATH=src python3 -m pytest tests/test_skills.py -q
>       assert index_data["skills"][0]["slug"] == "a-skill"
E       AssertionError: assert 'z-skill' == 'a-skill'
E         - a-skill
E         + z-skill
tests/test_skills.py:300: AssertionError
FAILED tests/test_skills.py::test_build_index_data_is_sorted - AssertionError...
1 failed, 7 passed in 0.37s
```

Red, and red on exactly the one test that owns the guarantee. At `88530b3` the
identical mutation left all 8 green. The silent-vacuity pathology is gone.

## Claim 2, restoring the sort makes the suite green. CONFIRMED

Restored from a pre-mutation copy and proved the restore was exact before
trusting the green:

```
$ diff <(git show 6ffe808:src/vcf_ops_mcp/skills.py) src/vcf_ops_mcp/skills.py
RESTORED byte-identical

$ PYTHONPATH=src python3 -m pytest tests/test_skills.py -q
........                                                                 [100%]
8 passed in 0.29s

$ PYTHONPATH=src python3 -m pytest tests/ -q
...............                                                          [100%]
15 passed in 0.32s
```

8 of 8 and 15 of 15 as claimed. No skips, no deselects.

## Claim 3, monkeypatch scoping and order-independence. CONFIRMED

The undo is the `monkeypatch` fixture, not a manual restore. Confirmed
structurally, there is no hand-rolled teardown that could be skipped on a failing
assertion:

```
manual `Path.iterdir = ...` reassignments in the test body: 0
```

`monkeypatch.setattr(Path, "iterdir", mock_iterdir)` is class-level, so leakage
was the thing worth testing rather than assuming. Three ways, all clean:

```
$ PYTHONPATH=src python3 -m pytest tests/test_skills.py -q        # alone
8 passed

$ PYTHONPATH=src python3 -m pytest tests/ -q                      # whole suite
15 passed

$ PYTHONPATH=src python3 -m pytest tests/test_skills.py::test_build_index_data_is_sorted tests/ -q
15 passed                                                          # sort test forced first
```

Ordering the sort test ahead of everything else is the arrangement that would
expose a leak, and it is green. I also dropped a probe test into the suite that
asserts `Path.iterdir` is pristine after the fact:

```python
def test_zz_iterdir_is_pristine():
    assert Path.iterdir.__module__ == 'pathlib'
    assert 'mock_iterdir' not in getattr(Path.iterdir, '__qualname__', '')
```

```
$ PYTHONPATH=src python3 -m pytest tests/ -q
16 passed in 0.30s
```

The real `pathlib.Path.iterdir` is back on the class once the test finishes. The
probe was removed; it is not part of the reviewed tree.

## Claim 4, the patch intercepts only the skills directory. CONFIRMED

```python
def mock_iterdir(self):
    results = list(original_iterdir(self))
    if self == skills_dir:
        return iter(sorted(results, key=lambda p: p.name, reverse=True))
    return iter(results)
```

One guard, `if self == skills_dir`, and one unconditional passthrough returning
the unmodified `original_iterdir` result for every other path. It cannot mask a
failure elsewhere in the call because it changes nothing elsewhere in the call.

Worth stating that this is not merely read off the source: the mutation in claim
1 proves the reversed order actually reached `build_index_data` and actually
survived to the output when the sort was absent. A patch that had failed to
intercept would have left the test green under mutation, which is precisely the
`88530b3` failure mode. It went red, so the intercept is live.

## Claim 5, the sort is byte-identical to `88530b3`. CONFIRMED

Same text, same line number, unmoved by the whitespace commit:

```
$ git show 88530b3:src/vcf_ops_mcp/skills.py | grep -n '\.sort('
214:            versions.sort(key=lambda v: [int(x) if x.isdigit() else x for x in v.replace('-', '.').split('.')])
217:    catalog.sort(key=lambda x: (x["slug"], x["version"]))
233:    existing_catalog.sort(key=lambda x: (x["slug"], x["version"]))

$ git show 6ffe808:src/vcf_ops_mcp/skills.py | grep -n '\.sort('
214:            versions.sort(key=lambda v: [int(x) if x.isdigit() else x for x in v.replace('-', '.').split('.')])
217:    catalog.sort(key=lambda x: (x["slug"], x["version"]))
233:    existing_catalog.sort(key=lambda x: (x["slug"], x["version"]))
```

Stronger than the claim asked for, `skills.py` in its entirety is unchanged
between `88530b3` and the head once whitespace is ignored:

```
$ git diff -w --stat 88530b3 6ffe808 -- src/vcf_ops_mcp/skills.py
(empty)
```

So everything I verified about that file at `88530b3` transfers without
re-derivation, and the only semantic change in the range is the test.

## Claim 6, the whitespace commit is genuinely whitespace-only. CONFIRMED

```
$ git diff -w ed8eabb 6ffe808
(empty, exit 0)

$ git diff --numstat ed8eabb 6ffe808
12	12	src/vcf_ops_mcp/skills.py
43	43	tests/test_skills.py
```

Equal additions and deletions per file, so no line was deleted and nothing
shifted. Inspected the raw bytes to confirm the change is what it claims rather
than trusting `-w` alone:

```
$ git diff ed8eabb 6ffe808 | cat -A | grep '^[-+]'
-    $
+$
-            $
+$
-                $
+$
...
```

Every changed line is a blank line losing its trailing indentation. No content
line touched.

## Claim 7, `git diff --check`. CONFIRMED

```
$ git diff --check 33bca5d 6ffe808
(no output)
check exit=0
```

## Claim 8, items 1 and 3 have not regressed. CONFIRMED

`skills.py` is unchanged modulo whitespace across the range (claim 5), which
covers this structurally, but I re-ran the behavior rather than resting on that.

The digest is still verified ahead of the placeholder skip. `_calculate_sha256`
and the `actual_digest != meta.content_sha256` raise sit at `skills.py:160-165`;
the `if meta.maturity == "placeholder"` skip and its `continue` sit at
`skills.py:168-169`. Verification precedes the skip, so a placeholder is still
not a hole for smuggling unverified content.

All four render paths still refuse the placeholder, exercised against the real
catalog:

```
catalog slugs   : ['actions-how-to', 'metrics-query-patterns']
resource uris   : ['skill://actions-how-to/1.0.0', 'skill://metrics-query-patterns/1.0.0',
                   'skill://actions-how-to/current', 'skill://metrics-query-patterns/current']
prompts         : ['use_actions-how-to', 'use_metrics-query-patterns']
list_skills     : ['actions-how-to', 'metrics-query-patterns']
read_resource(placeholder) : None
read_prompt(placeholder)   : None
get_skill(placeholder)     : None
```

The two enumeration paths omit it and the three lookup paths return `None`
rather than content. Item 3's tests
(`test_check_index_exact_regeneration_tampered`,
`test_check_index_exact_regeneration_real_repo`) are both present and both in the
green 8.

## Claim 9, `skills/index.json` regenerates byte-identical, twice. CONFIRMED

```
$ sha256sum skills/index.json                    # as committed
e7b34502c311fc310fdee2de79025b4795ab4c13f7839783f33b0076fdc96abb

$ python3 tools/generate_skills_index.py; sha256sum skills/index.json
e7b34502c311fc310fdee2de79025b4795ab4c13f7839783f33b0076fdc96abb

$ python3 tools/generate_skills_index.py; sha256sum skills/index.json
e7b34502c311fc310fdee2de79025b4795ab4c13f7839783f33b0076fdc96abb

$ diff /tmp/index.orig.json skills/index.json
BYTE-IDENTICAL after 2 regenerations
```

Same digest across the committed file and both regenerations. A CI step of the
shape "regenerate and `git diff --exit-code`" stays safe.

## Claim 10, trailers on both new commits. CONFIRMED

```
6ffe808  Fix trailing whitespace
         Co-authored-by: agy-worker <agy@team.local>
ed8eabb  tests: monkeypatch iterdir to guard skill sorting
         Co-authored-by: agy-worker <agy@team.local>
```

Exact, on both.

## Claim 11, `commit_msg.txt` is gone. CONFIRMED

```
$ ls -la commit_msg.txt
ls: cannot access 'commit_msg.txt': No such file or directory

$ git log --all --oneline -- commit_msg.txt
(no output)
```

Absent from the author's worktree and never committed on any branch.

## Constitution checks on the range

**No em-dashes or en-dashes.** Clean in both touched files at the head:

```
$ grep -n '[em-dash or en-dash]' src/vcf_ops_mcp/skills.py tests/test_skills.py
(no matches, exit 1)
```

**Author's worktree untouched.** `git status --porcelain --untracked-files=no`
empty at the end of the review, as it was at the start.

## The one out-of-scope item, restated and not held

`catalog.current` still carries the placeholder slug:

```
current map: {'actions-how-to': '1.0.0', 'metrics-query-patterns': '1.0.0',
              'suite-api-auth-walkthrough': '1.0.0'}
```

Unchanged from what I recorded at `88530b3`, no worse. Every render path is
guarded, so this slice's contract is correct. It matters only if the delivery
slice iterates `catalog.current` directly instead of `get_prompts()` and
`get_resource_uris()`. It is recorded for delivery and is explicitly not a defect
of this slice; I am not withholding over it.

## Summary

Signed. The hold is closed for the right reason: not because a test was added,
but because I deleted the sort and watched the test go red, then restored it
byte-identically and watched the suite go green. The monkeypatch is scoped to the
skills directory, passes through everywhere else, and is undone by the fixture
with no leak into any other test in any ordering I could construct. The
whitespace commit is provably whitespace-only and left the sort untouched. Items
1 and 3 hold. Index regeneration is deterministic.

`agy/r3-skills` at `6ffe808d96635943fe3c56c69a05458749efe68d` is clear for
integration into the round branch.

Co-authored-by: claude-worker <claude@team.local>
