"""Reliability and cost-spread metrics. Formulas are documented in docs/METRICS.md.

Everything here is a pure function of the run records so it can be tested exactly.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from itertools import combinations

from .workspace import changed_lines

Z95 = 1.959963984540054


# ---- binomial pass-rate statistics ----------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (Wilson 1927)."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if successes == 0 else max(0.0, centre - half)
    hi = 1.0 if successes == n else min(1.0, centre + half)
    return (lo, hi)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator of P(at least one of k runs passes) (Chen et al. 2021)."""
    if k > n:
        raise ValueError("k must be <= n")
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator of P(all k runs pass), "pass^k" (Yao et al. 2024, tau-bench)."""
    if k > n:
        raise ValueError("k must be <= n")
    return math.comb(c, k) / math.comb(n, k)


def flip_rate(n: int, c: int) -> float | None:
    """Probability that two distinct runs of the same task disagree on pass/fail.

    Equals 2c(n-c) / (n(n-1)), the unbiased estimator of 2p(1-p). Order-independent.
    """
    if n < 2:
        return None
    return 2 * c * (n - c) / (n * (n - 1))


# ---- spread statistics -----------------------------------------------------------------


def spread(values: list[float | int | None]) -> dict:
    """mean, median, sample std (ddof=1), CV = std/mean, min, max, IQR. Ignores ``None``."""
    xs = [float(v) for v in values if v is not None]
    out: dict = {"n": len(xs), "n_missing": len(values) - len(xs)}
    if not xs:
        return out | {k: None for k in ("mean", "median", "std", "cv", "min", "max", "iqr")}
    mean = statistics.fmean(xs)
    std = statistics.stdev(xs) if len(xs) >= 2 else None
    cv = (std / mean) if (std is not None and mean > 0) else None
    if len(xs) >= 2:
        q = statistics.quantiles(xs, n=4, method="inclusive")
        iqr = q[2] - q[0]
    else:
        iqr = None
    return out | {
        "mean": mean,
        "median": statistics.median(xs),
        "std": std,
        "cv": cv,
        "min": min(xs),
        "max": max(xs),
        "iqr": iqr,
    }


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def approach_similarity(diffs: list[str]) -> float | None:
    """Mean pairwise Jaccard similarity of changed-line sets. ``None`` if fewer than 2 diffs."""
    if len(diffs) < 2:
        return None
    sets = [changed_lines(d) for d in diffs]
    pairs = [jaccard(a, b) for a, b in combinations(sets, 2)]
    return statistics.fmean(pairs)


def _mean(xs: list[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return statistics.fmean(vals) if vals else None


def bootstrap_task_ci(
    per_task_rates: list[float], reps: int = 2000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float] | None:
    """Percentile bootstrap CI for the macro pass rate, resampling *tasks* with replacement.

    This reflects uncertainty about the task population, which the pooled Wilson interval
    (which treats every run as independent) does not.
    """
    m = len(per_task_rates)
    if m < 2:
        return None
    rng = random.Random(seed)
    stats = sorted(statistics.fmean(rng.choices(per_task_rates, k=m)) for _ in range(reps))
    lo = stats[int(math.floor(alpha / 2 * reps))]
    hi = stats[min(int(math.ceil((1 - alpha / 2) * reps)) - 1, reps - 1)]
    return (lo, hi)


# ---- per-task and per-agent rollups ---------------------------------------------------


def task_metrics(task_runs: list[dict], diffs: dict[int, str] | None = None) -> dict:
    runs = sorted(task_runs, key=lambda r: r["run_index"])
    n = len(runs)
    c = sum(1 for r in runs if r["passed"])
    lo, hi = wilson_interval(c, n)
    passed_diffs = [
        diffs[r["run_index"]] for r in runs if r["passed"] and diffs and r["run_index"] in diffs
    ]
    return {
        "n": n,
        "passes": c,
        "pass_rate": c / n if n else None,
        "pass_rate_ci95": [lo, hi],
        "pass_at_k": {k: pass_at_k(n, c, k) for k in range(1, n + 1)},
        "pass_hat_k": {k: pass_hat_k(n, c, k) for k in range(1, n + 1)},
        "flip_rate": flip_rate(n, c),
        "outcomes": [bool(r["passed"]) for r in runs],
        "cost_usd": spread([r.get("cost_usd") for r in runs]),
        "total_tokens": spread([r.get("total_tokens") for r in runs]),
        "output_tokens": spread([r.get("output_tokens") for r in runs]),
        "wall_time_s": spread([r.get("wall_time_s") for r in runs]),
        "approach_similarity": approach_similarity(passed_diffs),
        "timeouts": sum(1 for r in runs if r.get("agent_timed_out")),
        "agent_errors": sum(1 for r in runs if r.get("agent_error")),
    }


def agent_metrics(
    runs: list[dict], diffs: dict[tuple[str, int], str] | None = None, k: int | None = None
) -> dict:
    """Roll up one result set (one agent, model and CLI version).

    ``k`` defaults to the smallest per-task run count so pass@k / pass^k are defined for
    every task.
    """
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        by_task[r["task_id"]].append(r)
    per_task = {}
    for tid, trs in sorted(by_task.items()):
        tdiffs = {i: d for (t, i), d in (diffs or {}).items() if t == tid}
        per_task[tid] = task_metrics(trs, tdiffs)
    n_total = sum(m["n"] for m in per_task.values())
    c_total = sum(m["passes"] for m in per_task.values())
    min_n = min((m["n"] for m in per_task.values()), default=0)
    k = min(k or min_n, min_n) if min_n else None
    rates = [m["pass_rate"] for m in per_task.values()]
    costs = [r.get("cost_usd") for r in runs]
    known_costs = [x for x in costs if x is not None]
    total_cost = sum(known_costs) if known_costs else None
    return {
        "n_tasks": len(per_task),
        "n_runs": n_total,
        "min_runs_per_task": min_n,
        "passes": c_total,
        "pass_rate": c_total / n_total if n_total else None,
        "pass_rate_ci95": list(wilson_interval(c_total, n_total)),
        "macro_pass_rate": _mean(rates),
        "macro_pass_rate_task_bootstrap_ci95": bootstrap_task_ci(rates),
        "k": k,
        "pass_at_k": _mean([m["pass_at_k"][k] for m in per_task.values()]) if k else None,
        "pass_hat_k": _mean([m["pass_hat_k"][k] for m in per_task.values()]) if k else None,
        "flip_rate": _mean([m["flip_rate"] for m in per_task.values()]),
        "flaky_task_fraction": (
            sum(1 for m in per_task.values() if 0 < m["passes"] < m["n"]) / len(per_task)
        )
        if per_task
        else None,
        "total_cost_usd": total_cost,
        "cost_reported_runs": len(known_costs),
        "mean_cost_usd": statistics.fmean(known_costs) if known_costs else None,
        "median_cost_usd": statistics.median(known_costs) if known_costs else None,
        "cost_per_success_usd": (total_cost / c_total)
        if (total_cost is not None and c_total)
        else None,
        "cost_cv_within_task": _mean([m["cost_usd"]["cv"] for m in per_task.values()]),
        "tokens_mean": spread([r.get("total_tokens") for r in runs])["mean"],
        "tokens_median": spread([r.get("total_tokens") for r in runs])["median"],
        "output_tokens_median": spread([r.get("output_tokens") for r in runs])["median"],
        "tokens_cv_within_task": _mean([m["total_tokens"]["cv"] for m in per_task.values()]),
        "wall_time_mean_s": spread([r.get("wall_time_s") for r in runs])["mean"],
        "wall_time_median_s": spread([r.get("wall_time_s") for r in runs])["median"],
        "wall_time_total_s": sum(r.get("wall_time_s") or 0.0 for r in runs),
        "wall_time_cv_within_task": _mean([m["wall_time_s"]["cv"] for m in per_task.values()]),
        "approach_similarity": _mean([m["approach_similarity"] for m in per_task.values()]),
        "per_task": per_task,
    }
