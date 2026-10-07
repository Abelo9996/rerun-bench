# rerun-bench report

Generated 2026-10-07T01:58:52+00:00 by rerun-bench 0.2.1. 3 result sets, 10 tasks, k = 10. Definitions: [docs/METRICS.md](https://github.com/Abelo9996/rerun-bench/blob/main/docs/METRICS.md).

- **Pass rate**: share of runs whose hidden verifier passed, with a 95% confidence interval (Wilson). Wide intervals mean too few runs to be precise.
- **pass^10**: chance that 10 reruns of the same task all pass. The number to watch if you run the agent once and trust the result.
- **pass@10**: chance that at least one of 10 reruns passes.
- **Flip rate**: chance that two runs of the same task disagree (one pass, one fail).
- **Flaky tasks**: share of tasks with at least one pass and at least one fail.
- **CV**: run-to-run spread on the same task (standard deviation / mean), averaged over tasks. 0 means identical every run.

## Reliability

| Agent / model | CLI version | Runs/task | Pass rate [95% CI] | pass^10 | pass@10 | Flip rate | Flaky tasks |
|---|---|---|---|---|---|---|---|
| claude / claude-opus-4-8 | 2.1.291 (Claude Code) | 10 | 100% [96, 100] | 100% | 100% | 0% | 0% |
| claude / claude-opus-5-5 | 2.1.292 (Claude Code) | 10 | 100% [96, 100] | 100% | 100% | 0% | 0% |
| codex / gpt-6-luna | codex-cli 0.160.0 | 10 | 96% [90, 98] | 70% | 100% | 8% | 30% |

## Cost and run-to-run spread

| Agent / model | Median cost/run | Mean cost/run | Cost CV | Median tokens/run | Tokens CV | Median wall time | Wall CV | Approach sim. |
|---|---|---|---|---|---|---|---|---|
| claude / claude-opus-4-8 | $0.1312 | $0.1522 | 0.08 | 84,534 | 0.13 | 15.6s | 0.22 | 0.82 |
| claude / claude-opus-5-5 | $0.0899 | $0.0972 | 0.04 | 53,368 | 0.08 | 12.7s | 0.20 | 0.82 |
| codex / gpt-6-luna | n/a | n/a | n/a | 56,552 | 0.16 | 16.8s | 0.90 | 0.75 |

## Comparison

The pass-rate 95% intervals of all rows overlap, so these runs are not enough to tell the rows apart. More runs per task narrow the intervals. Overlap is used as a deliberately cautious test because runs of the same task are not independent; the JSON report also has a task-bootstrap interval (macro_pass_rate_task_bootstrap_ci95). Rows are sorted by pass^10, then pass rate. The order is not a ranking.

## Notes

- codex / gpt-6-luna (`codex`): Cost: not reported by this CLI. For codex, pass prices with --agent-opt usd_per_mtok_in=... usd_per_mtok_out=...

## Per-task consistency

Outcomes in run order (P = pass, F = fail), then pass rate, flip rate, and cost CV.

| Task | claude / claude-opus-4-8 | claude / claude-opus-5-5 | codex / gpt-6-luna |
|---|---|---|---|
| add-cli-flag | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.01 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.11 | `PPPPPFPPPP` 90%, flip 20%, cost CV n/a |
| edit-config | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.07 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.06 | `PPPPPPPPPP` 100%, flip 0%, cost CV n/a |
| fix-failing-test | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.01 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.02 | `PPPPPPPPPP` 100%, flip 0%, cost CV n/a |
| follow-agents-md | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.01 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.01 | `PPPPPPPPPP` 100%, flip 0%, cost CV n/a |
| implement-lru-cache | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.13 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.02 | `PPPPPPPPPP` 100%, flip 0%, cost CV n/a |
| implement-slugify | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.19 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.02 | `PPPPPPPFPP` 90%, flip 20%, cost CV n/a |
| minimal-fix | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.05 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.02 | `PPPPPPPPPP` 100%, flip 0%, cost CV n/a |
| multi-file-rename | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.16 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.07 | `PPPPPPPPPP` 100%, flip 0%, cost CV n/a |
| refactor-extract-helper | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.05 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.04 | `PPPPPPPFPF` 80%, flip 36%, cost CV n/a |
| write-tests | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.11 | `PPPPPPPPPP` 100%, flip 0%, cost CV 0.07 | `PPPPPPPPPP` 100%, flip 0%, cost CV n/a |
