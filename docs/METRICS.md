# Metrics

All metrics are computed from the per-run records in `runs.jsonl` by
`src/rerunbench/metrics.py`. Every formula below has a unit test in `tests/test_metrics.py`.

## Notation

For one result set (one agent, model and CLI version):

- `T` tasks, indexed by `t`.
- `n_t` runs of task `t`; `c_t` of them pass the task's verifier.
- A run passes if and only if `verify.py` exits 0. The agent's own exit code, self-reported
  success, and output text are recorded but never used to score.
- `k` defaults to `min_t n_t` (the runs per task), so every task has pass@k and pass^k
  defined. Override with `rerunbench report --k`.

## Sampling design

- Each run starts from a fresh temporary copy of the task workspace. No state carries over.
- Runs are interleaved: run 0 of every task, then run 1 of every task, and so on. Session-level
  drift (rate limiting, a provider-side model change mid-session) is then spread across tasks
  instead of concentrated on whichever task ran last.
- Runs of the same task are treated as independent Bernoulli trials with a task-specific
  success probability `p_t`. Runs of different tasks are not exchangeable.

## Pass rate

| Name | Formula | Notes |
|---|---|---|
| Pass rate (pooled) | `sum_t c_t / sum_t n_t` | Shown with a Wilson 95% interval. |
| Wilson interval | `(p + z^2/2N +/- z sqrt(p(1-p)/N + z^2/4N^2)) / (1 + z^2/N)`, `z = 1.95996` | Wilson (1927). Well behaved at `p` near 0 or 1 and small `N`, unlike the normal approximation. Endpoints are exactly 0 or 1 when `c = 0` or `c = N`. |
| Macro pass rate | `(1/T) sum_t c_t / n_t` | Equals the pooled rate when every task has the same `n`. |
| Task-bootstrap 95% CI | percentile interval of the macro pass rate over 2000 resamples of tasks with replacement, seed 0 | Captures uncertainty about the task population. The pooled Wilson interval treats every run as independent and so understates between-task uncertainty; use the bootstrap interval when comparing agents across the suite. Both are in the JSON report. |

## Reliability across reruns

| Name | Per-task estimator | Aggregate | Reference |
|---|---|---|---|
| pass@k | `1 - C(n-c, k) / C(n, k)` | mean over tasks | Chen et al. 2021 (Codex paper). Unbiased for `1 - (1-p)^k`: the chance that at least one of `k` attempts succeeds. |
| pass^k | `C(c, k) / C(n, k)` | mean over tasks | Yao et al. 2024 (tau-bench). Unbiased for `p^k`: the chance that all `k` attempts succeed. This is the number to watch if you run an agent once and trust the result. |
| Flip rate | `2 c (n - c) / (n (n - 1))` | mean over tasks | Probability that two distinct runs of the same task disagree. Unbiased for `2p(1-p)`. Order-independent, so it does not depend on the sequence in which runs happened. 0 means fully consistent (always pass or always fail). The maximum is reached when `c` is closest to `n/2` and is slightly above 0.5 for small `n` (0.6 at `n = 5`). |
| Flaky task fraction | `1[0 < c_t < n_t]` | mean over tasks | Share of tasks with at least one pass and at least one fail. Coarser than flip rate and grows with `n`. |

`pass^k <= pass@1 <= pass@k` always holds. The gap between pass@k and pass^k is the cost
of inconsistency.

## Cost, tokens and wall time

For a per-run quantity `x` (cost in USD, total tokens, wall seconds) over the runs of one task:

| Name | Formula |
|---|---|
| mean, median | usual definitions |
| std | sample standard deviation, `ddof = 1` |
| CV | `std / mean` (undefined if `mean = 0` or fewer than 2 values) |
| IQR | `Q3 - Q1`, inclusive quartile method |

The leaderboard reports the **mean within-task CV**: compute CV across reruns of each task,
then average over tasks. CV across all runs would mostly measure how different the tasks are
from each other, not how consistent the agent is.

Other cost figures: total cost, mean cost per run, and **cost per success** =
`total cost / total passes`.

Missing data: a CLI that does not report a value yields `null`, never 0. Statistics skip
nulls, and `cost_reported_runs` says how many runs contributed. Total tokens = input +
output + cache read + cache write as reported by the CLI.

Wall time is measured around the agent process only (verifier time excluded). The mock
adapter reports simulated wall time so demos run in seconds.

## Approach consistency (diff similarity)

For each run, the harness stores a unified diff of the workspace against its starting state.
For the passing runs of a task:

1. Turn each diff into a set of changed lines: `"<path>:+<line>"` and `"<path>:-<line>"`,
   trailing whitespace stripped, context lines ignored.
2. Compute Jaccard similarity `|A & B| / |A | B|` for every pair of passing runs.
3. Report the mean over pairs (undefined with fewer than 2 passing runs).

The leaderboard value is the mean over tasks where it is defined. A value of 1.0 means every
passing run made the same edit. Low values with a high pass rate mean the agent reaches correct
answers by different routes, which matters for code review load and for reproducing a fix.

Limitations: line-level Jaccard is sensitive to formatting (the same logical change written
with different line breaks counts as a different approach) and ignores line order. It is a
signal for variability, not a measure of code quality.

## What is not measured (yet)

- Statistical tests between two result sets (planned: Fisher exact test per task, and a
  paired task-level bootstrap for the macro difference).
- Variance decomposition across CLI versions and days.
