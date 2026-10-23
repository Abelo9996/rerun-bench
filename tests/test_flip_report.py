"""The flip-first report that ``mine`` and ``from-test`` lead with."""

from __future__ import annotations

import json

from rerun_bench import card as card_mod
from rerun_bench import report as report_mod


def _run_rec(task_id, idx, passed, **kw):
    rec = {
        "task_id": task_id,
        "run_index": idx,
        "passed": passed,
        "wall_time_s": 2.0 + idx,
        "total_tokens": 10000 + idx * 100,
        "cost_usd": 0.05,
        "lines_added": 1,
        "lines_removed": 1,
        "files_changed": ["calc.py"],
        "diff_path": f"diffs/{task_id}/run{idx:03d}.diff",
        "verify_output_tail": "assert 8 == 2\nFAILED test_calc.py::test_sub" if not passed else "",
    }
    rec.update(kw)
    return rec


def _write_results(tmp_path, rows):
    d = tmp_path / "r"
    d.mkdir()
    meta = {
        "schema_version": 1,
        "run_id": "claude_default_x",
        "agent": "claude",
        "model": None,
        "runs_per_task": max(r["run_index"] for r in rows) + 1,
        "tasks": sorted({r["task_id"] for r in rows}),
        "started_at": "2026-10-23T00:00:00+00:00",
    }
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with (d / "runs.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows:
        p = d / r["diff_path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        change = "-    return a + b\n+    return a - b\n" if r["passed"] else "+    pass\n"
        p.write_text(f"--- a/calc.py\n+++ b/calc.py\n@@ -1 +1 @@\n{change}", encoding="utf-8")
    return d


def test_flip_report_leads_with_the_breakdown(tmp_path):
    rows = (
        [_run_rec("fixed-one", i, True) for i in range(3)]
        + [_run_rec("flaky-one", i, i != 1) for i in range(3)]
        + [_run_rec("never-one", i, False) for i in range(3)]
    )
    d = _write_results(tmp_path, rows)
    text = report_mod.to_flip_text(d)
    first = text.splitlines()[0]
    assert "replayed 3 of your past fixes, 3 runs each" in first
    assert "1 fixed reliably" in first and "1 flaky" in first and "1 never" in first
    assert "passed 3/3" in text and "passed 2/3" in text and "passed 0/3" in text
    assert "FLAKY" in text


def test_flip_report_shows_a_pass_and_a_fail_for_flaky_tasks(tmp_path):
    rows = [_run_rec("flaky-one", i, i != 1) for i in range(3)]
    d = _write_results(tmp_path, rows)
    text = report_mod.to_flip_text(d)
    assert "Flip: flaky-one" in text
    assert "PASS  run" in text and "FAIL  run" in text
    # The passing run's diff and the failing run's test output both appear.
    assert "return a - b" in text
    assert "test output:" in text
    assert "assert 8 == 2" in text
    # The aggregate follows.
    assert "Aggregate" in text and "Flip rate" in text


def test_no_flips_states_it_plainly(tmp_path):
    rows = [_run_rec("fixed-one", i, True) for i in range(3)]
    d = _write_results(tmp_path, rows)
    text = report_mod.to_flip_text(d)
    assert "No flips" in text


def test_mined_card_uses_the_flip_headline(tmp_path):
    rows = (
        [_run_rec("fixed-one", i, True) for i in range(3)]
        + [_run_rec("flaky-one", i, i != 1) for i in range(3)]
    )
    d = _write_results(tmp_path, rows)
    rep = report_mod.build(d)
    model = card_mod.card_model(rep, mined=True)
    assert model["sentence"].startswith("Replayed 2 of your past fixes")
    svg = card_mod.render_svg(model)
    assert svg.startswith("<svg") and "1200" in svg
