# Pilot run, 2026-10-03

This is a pilot: 3 runs per task, 10 tasks, two agents. With n = 3 per task, a single
failure moves a task's pass rate by 33 points, and the confidence intervals below are wide.
It is a check that the harness works end to end against real CLIs, not a leaderboard.

## What was run

| | Claude Code | Codex CLI |
|---|---|---|
| Adapter | `claude` | `codex` |
| CLI version | 2.1.288 | 0.160.0 (npm package `@openai/codex@0.160.0`) |
| Model | CLI default, reported as `claude-opus-5-5` | `gpt-6-luna`, the model Codex 0.160.0 selects when no model is configured |
| Model flag | none | `--model gpt-6-luna` (see note 2) |
| Command | `rerun-bench run --agent claude --tasks all --runs 3 --run-id claude --yes` | `rerun-bench run --agent codex --model gpt-6-luna --tasks all --runs 3 --run-id codex --yes` |
| Isolation | default (`--setting-sources project,local --strict-mcp-config`) | default (`--ignore-user-config`) |
| Runs | 10 tasks x 3 = 30 | 10 tasks x 3 = 30 |

- Date: 2026-10-03, 08:16 to 08:25 UTC. The two agents ran at the same time, each with
  `--jobs 1`.
- Machine: macOS 26.2 (Darwin 25.2.0), Apple Silicon (arm64), Python 3.13.15.
- Harness: rerun-bench 0.1.0, code identical to commit `7a2bef2`.
- Task timeouts: the suite defaults (300 s for `edit-config`, 600 s for the rest). No run
  timed out.
- Authentication: a Claude subscription login for `claude` and a ChatGPT login for `codex`.

Notes:

1. The Homebrew Codex CLI on this machine was 0.142.5. Its default model, `gpt-5.5`,
   returned `404 Not Found: The model gpt-5.5 does not exist or you do not have access to
   it` on this account, both with and without the user config. The other model names tried
   (`gpt-5`, `gpt-5-codex`, `gpt-5.4`, and others) were rejected as not supported with a
   ChatGPT login. Codex 0.160.0 (current on npm that day) ran
   without errors, so the pilot used it, placed first on `PATH`.
2. `codex exec --json` does not report the model. Codex 0.160.0 prints `model: gpt-6-luna`
   in its startup header when run with `--ignore-user-config` and no `--model`, and the
   same header (including reasoning effort) when `--model gpt-6-luna` is passed. The flag
   was passed so the model is recorded in the results.
3. Claude Code reports cost as `total_cost_usd`, computed at list prices. On a subscription
   login this is quota used, not money billed. Codex reports tokens only, so its cost
   columns are `n/a`.

## Headline numbers

| | Claude Code / claude-opus-5-5 | Codex / gpt-6-luna |
|---|---|---|
| Pass rate, Wilson 95% CI | 30/30 = 100% [89, 100] | 28/30 = 93% [79, 98] |
| Macro pass rate, task-bootstrap 95% CI | 100% [100, 100] | 93% [83, 100] |
| pass@3 | 100% | 100% |
| pass^3 | 100% | 80% |
| Flip rate | 0% | 13% |
| Flaky tasks | 0 of 10 | 2 of 10 |
| Median cost per run | $0.0886 (mean $0.0938) | not reported |
| Total reported cost | $2.82 | not reported |
| Median total tokens per run | 52,017 | 56,629 |
| Median output tokens per run | 964 | 516 |
| Total tokens, all 30 runs | 1,731,413 | 1,955,466 |
| Median wall time per run | 12.6 s | 16.1 s |
| Summed agent wall time | 413 s | 520 s |
| Within-task tokens CV | 0.04 | 0.14 |
| Approach similarity (passing diffs) | 0.81 | 0.77 |

The two Wilson intervals overlap, so this pilot does not establish a difference in pass
rate between the two agents. Total tokens include cache reads, which are most of the count
for both CLIs (1.47 M of 1.73 M for Claude Code, 1.72 M of 1.96 M for Codex). `num_turns`
is not comparable across CLIs: Claude Code counts model turns, Codex counts user turns
(always 1 here).

## Failures

Both failures were Codex runs. Each task passed the other two times, and the verifiers
were checked against the recorded diffs:

- `implement-lru-cache`, run 0: `put` returned the evicted value instead of the evicted
  key (`_, evicted = self._items.popitem(last=False)`). The docstring says "evict the least
  recently used key and return it", and the verifier checks for the key. Agent error.
- `refactor-extract-helper`, run 1: the agent exited 0 after 8.7 s with no file changes.
  This harness version did not record the agent's output, so the reason is not known.
  Three later diagnostic runs of the same task (not part of these results) all passed.
  Run records now include `agent_stdout_tail` and `agent_stderr_tail` so a failure like this
  can be diagnosed from the result files.

No task failed for a reason outside the agent's control, so no task was changed after the
pilot. One environment detail seen in the diagnostic runs: task workspaces are not git
repositories, so an agent that runs `git diff` to review its work gets an error (exit 129)
and has to check its changes another way. No run failed because of it.

## Files

- `results/claude/`, `results/codex/`: `meta.json`, `runs.jsonl` (one record per run) and
  `diffs/<task>/runNNN.diff` for every run.
- `report.md`, `report.json`, `report.html`: generated with
  `rerun-bench report docs/pilot-2026-10-03/results --format <md|json|html>`.
- `card.svg`: the 1200x630 result card, generated with
  `rerun-bench card docs/pilot-2026-10-03/report.json -o docs/pilot-2026-10-03/card.svg`.
  `card.png` is the same card converted with `rsvg-convert`, ready to post.

Reproduce (spends quota on both accounts):

```sh
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude --yes
rerun-bench run --agent codex --model gpt-6-luna --tasks all --runs 3 --out results/ --run-id codex --yes
rerun-bench report results/ --format md
```
