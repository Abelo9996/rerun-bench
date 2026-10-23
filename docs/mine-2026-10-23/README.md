# 2026-10-23: `rerun-bench mine` on four public repositories

Real runs of `rerun-bench mine` against Claude Code, replaying each repository's own past
bug-fix commits. They validate the one-call path end to end, including dependency install:
mine the git history, build one dependency environment per repository, run the agent, and lead
with the flip.

- Agent: Claude Code 2.1.308, default model (reported as `claude-opus-5-5`).
- 2 to 3 mined fixes per repository, 3 runs each (30 agent runs in all).
- Two repositories are pure-Python with no third-party deps; two have third-party test
  dependencies that mine installed automatically.

## Result

Claude Code reproduced every mined fix reliably: 30 of 30 runs passed, flip rate 0%. No fix
flipped on any repository; when one does, the report shows one passing and one failing run side
by side (diff, failing test output, wall time, tokens).

| Repository | Deps installed | Pass rate | pass^3 | Flip | Median cost/run |
|---|---|---|---|---|---|
| [cachetools](https://github.com/tkem/cachetools) (Python) | none needed | 100% (9/9) | 100% | 0% | $0.2367 |
| [inflection](https://github.com/jpvanhal/inflection) (Python) | none needed | 100% (9/9) | 100% | 0% | $0.1136 |
| [furl](https://github.com/gruns/furl) (Python) | `uv pip install .` (0.5s) | 100% (6/6) | 100% | 0% | $0.1734 |
| [sindresorhus/slugify](https://github.com/sindresorhus/slugify) (JavaScript) | `npm install` (2.8s) | 100% (6/6) | 100% | 0% | $0.1543 |

![cachetools card](cachetools-card.png)

![furl card](furl-card.png)

![slugify card](slugify-card.png)

The 95% interval is wide (down to [61, 100]) because each repository is a small sample; it is
not evidence of flakiness. Raw run records are in `<repo>/runs.jsonl` and each run's diff is
under `<repo>/diffs/<task>/`.

## Dependencies and test narrowing

furl's tests import `orderedmultidict` and `six`; slugify's run under `ava`. mine built one
environment per repository (a uv virtualenv, then `uv pip install .`; or `npm install`) once
and reused it for both the parent and the commit worktree of every candidate. The Python
install is non-editable so the per-commit worktree source (placed on `PYTHONPATH`) shadows the
copy in site-packages, keeping the parent and commit distinct.

furl's suite is a single large `tests/test_furl.py` with tests that fail for unrelated reasons
at some commits. Each replay was narrowed to the tests the fix commit touched (pytest `-k`), so
those unrelated failures did not make a real fix look unreplayable. Commits whose own test
still did not pass on the fix commit were skipped with that reason, not built.

## Reproduce

```sh
uvx rerun-bench mine tkem/cachetools -n 3 --runs 3 --agent claude --yes
uvx rerun-bench mine jpvanhal/inflection -n 3 --runs 3 --agent claude --yes
uvx rerun-bench mine gruns/furl -n 2 --runs 3 --agent claude --yes
uvx rerun-bench mine sindresorhus/slugify -n 2 --runs 3 --agent claude --yes
```

Mining re-clones the repository into a scratch directory and removes it afterwards, so the exact
commits chosen depend on the history at the time; the ranking (clear fix wording, small diffs,
fast tests) is deterministic.
