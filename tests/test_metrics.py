import math

import pytest

from rerun_bench import metrics as m


def test_wilson_known_values():
    lo, hi = m.wilson_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4)
    assert hi == pytest.approx(0.7634, abs=1e-4)
    lo, hi = m.wilson_interval(0, 10)
    assert lo == 0.0
    assert hi == pytest.approx(m.Z95**2 / (10 + m.Z95**2), abs=1e-12)
    lo, hi = m.wilson_interval(10, 10)
    assert hi == 1.0 and lo == pytest.approx(1 - 0.2775, abs=1e-4)
    assert m.wilson_interval(0, 0) == (0.0, 1.0)


def test_pass_at_k_and_pass_hat_k():
    assert m.pass_at_k(5, 0, 3) == 0.0
    assert m.pass_at_k(5, 5, 3) == 1.0
    assert m.pass_at_k(5, 1, 1) == pytest.approx(0.2)
    assert m.pass_at_k(5, 2, 2) == pytest.approx(1 - math.comb(3, 2) / math.comb(5, 2))
    assert m.pass_hat_k(5, 5, 5) == 1.0
    assert m.pass_hat_k(5, 4, 5) == 0.0
    assert m.pass_hat_k(5, 4, 2) == pytest.approx(math.comb(4, 2) / math.comb(5, 2))
    for n in range(1, 7):
        for c in range(n + 1):
            assert m.pass_at_k(n, c, 1) == pytest.approx(c / n)
            assert m.pass_hat_k(n, c, 1) == pytest.approx(c / n)
            for k in range(1, n + 1):
                assert m.pass_hat_k(n, c, k) <= m.pass_at_k(n, c, k) + 1e-12
    with pytest.raises(ValueError):
        m.pass_at_k(3, 1, 4)


def test_pass_hat_k_is_unbiased_for_p_to_the_k():
    # E[C(c,k)/C(n,k)] over c ~ Binomial(n, p) equals p^k exactly.
    n, k, p = 6, 3, 0.7
    expect = sum(
        math.comb(n, c) * p**c * (1 - p) ** (n - c) * m.pass_hat_k(n, c, k) for c in range(n + 1)
    )
    assert expect == pytest.approx(p**k)


def test_flip_rate():
    assert m.flip_rate(1, 1) is None
    assert m.flip_rate(5, 5) == 0.0
    assert m.flip_rate(5, 0) == 0.0
    assert m.flip_rate(2, 1) == 1.0
    assert m.flip_rate(4, 2) == pytest.approx(2 * 2 * 2 / (4 * 3))
    # unbiased for 2p(1-p)
    n, p = 5, 0.3
    expect = sum(
        math.comb(n, c) * p**c * (1 - p) ** (n - c) * m.flip_rate(n, c) for c in range(n + 1)
    )
    assert expect == pytest.approx(2 * p * (1 - p))


def test_spread():
    s = m.spread([1, 2, 3, 4, None])
    assert s["n"] == 4 and s["n_missing"] == 1
    assert s["mean"] == 2.5 and s["median"] == 2.5
    assert s["std"] == pytest.approx(1.2909944)
    assert s["cv"] == pytest.approx(1.2909944 / 2.5)
    assert s["iqr"] == pytest.approx(1.5)
    assert m.spread([None, None])["mean"] is None
    assert m.spread([7])["cv"] is None
    assert m.spread([0, 0])["cv"] is None


def test_jaccard_and_similarity():
    assert m.jaccard(set(), set()) == 1.0
    assert m.jaccard({1, 2}, {2, 3}) == pytest.approx(1 / 3)
    d1 = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    d2 = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-x = 1\n+x = 3\n"
    assert m.approach_similarity([d1]) is None
    assert m.approach_similarity([d1, d1]) == 1.0
    assert m.approach_similarity([d1, d2]) == pytest.approx(1 / 3)


def test_bootstrap_deterministic():
    rates = [0.0, 0.2, 1.0, 0.8, 0.6]
    a = m.bootstrap_task_ci(rates)
    assert a == m.bootstrap_task_ci(rates)
    assert a[0] <= sum(rates) / len(rates) <= a[1]
    assert m.bootstrap_task_ci([0.5]) is None


def _runs(task, outcomes, cost=0.1):
    return [
        {
            "task_id": task,
            "run_index": i,
            "passed": o,
            "cost_usd": cost * (i + 1),
            "total_tokens": 100 * (i + 1),
            "wall_time_s": 10.0,
        }
        for i, o in enumerate(outcomes)
    ]


def test_agent_metrics_rollup():
    runs = _runs("a", [True] * 4) + _runs("b", [True, False, True, False]) + _runs("c", [False] * 4)
    r = m.agent_metrics(runs)
    assert r["n_tasks"] == 3 and r["n_runs"] == 12 and r["passes"] == 6
    assert r["pass_rate"] == 0.5 and r["k"] == 4
    assert r["pass_hat_k"] == pytest.approx(1 / 3)  # only task a passes all 4
    assert r["pass_at_k"] == pytest.approx(2 / 3)
    assert r["flaky_task_fraction"] == pytest.approx(1 / 3)
    assert r["flip_rate"] == pytest.approx((0 + 2 * 2 * 2 / 12 + 0) / 3)
    assert r["wall_time_cv_within_task"] == 0.0
    assert r["cost_per_success_usd"] == pytest.approx(r["total_cost_usd"] / 6)
    assert m.agent_metrics(runs, k=2)["k"] == 2


def test_agent_metrics_missing_cost():
    runs = [
        {
            "task_id": "a",
            "run_index": i,
            "passed": True,
            "cost_usd": None,
            "total_tokens": None,
            "wall_time_s": 1.0,
        }
        for i in range(3)
    ]
    r = m.agent_metrics(runs)
    assert r["total_cost_usd"] is None and r["cost_reported_runs"] == 0
    assert r["mean_cost_usd"] is None and r["cost_cv_within_task"] is None
