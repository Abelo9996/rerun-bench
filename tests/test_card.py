"""The shareable SVG result card: wording, validity, the simulated label, and the CLI."""

import json
import xml.etree.ElementTree as ET

import pytest

from rerun_bench import card, cli, report
from rerun_bench.metrics import wilson_interval

from .conftest import REPO, TASKS_DIR

PILOT = REPO / "docs" / "pilot-2026-10-03"
SVG_NS = "{http://www.w3.org/2000/svg}"
# En and em dash, from code points so this file contains neither.
DASHES = (chr(0x2013), chr(0x2014))


def entry(run_id, agent, model, passes, n, *, tasks=10, per_task=3, simulated=False, cost=0.05):
    return {
        "run_id": run_id,
        "agent": agent,
        "model": model,
        "simulated": simulated,
        "started_at": "2026-10-03T08:16:06+00:00",
        "metrics": {
            "n_tasks": tasks,
            "n_runs": n,
            "min_runs_per_task": per_task,
            "passes": passes,
            "pass_rate": passes / n,
            "pass_rate_ci95": list(wilson_interval(passes, n)),
            "pass_hat_k": 0.5,
            "flip_rate": 0.1,
            "median_cost_usd": cost,
            "per_task": {f"t{i}": {} for i in range(tasks)},
        },
    }


def rep_of(*entries):
    entries = list(entries)
    return {"k": 3, "entries": entries, "comparison": report.compare(entries)}


def assert_no_winner(text: str):
    low = text.lower()
    for w in card.WINNER_WORDS:
        assert w not in low, f"{w!r} in {text!r}"


def test_overlapping_intervals_never_name_a_winner():
    rep = rep_of(entry("a", "claude", "opus", 30, 30), entry("b", "codex", "gpt", 28, 30))
    assert all(p["intervals_overlap"] for p in rep["comparison"])
    s = card.sentence(rep)
    assert s == (
        "The 95% intervals of Claude Code and Codex CLI overlap, so these runs do not "
        "establish a difference in pass rate"
    )
    assert_no_winner(s)
    svg = card.to_svg(rep)
    assert_no_winner(svg.split("<style>")[0] + svg.split("</style>")[1])


def test_separate_intervals_are_stated_as_a_fact_about_the_intervals():
    rep = rep_of(entry("a", "claude", "opus", 29, 30), entry("b", "codex", "gpt", 5, 30))
    assert not rep["comparison"][0]["intervals_overlap"]
    s = card.sentence(rep)
    assert s == "The 95% intervals of Claude Code and Codex CLI do not overlap"
    assert_no_winner(s)
    three = rep_of(
        entry("a", "claude", "opus", 29, 30),
        entry("b", "codex", "gpt", 5, 30),
        entry("c", "opencode", "x", 6, 30),
    )
    assert card.sentence(three) == "2 of 3 pairs of 95% pass-rate intervals do not overlap"


def test_rows_that_ran_different_work_are_not_compared():
    rep = rep_of(entry("a", "claude", "opus", 30, 30), entry("b", "codex", "gpt", 9, 15, tasks=5))
    assert "not directly comparable" in card.sentence(rep)
    assert_no_winner(card.sentence(rep))


def test_one_result_set():
    s = card.sentence(rep_of(entry("a", "codex", "gpt", 28, 30)))
    assert s == "Codex CLI passed 28 of 30 runs (93%, 95% interval [79, 98])"


def test_rows_are_in_name_order_not_ranked():
    rep = rep_of(entry("z", "codex", "gpt", 30, 30), entry("y", "claude", "opus", 10, 30))
    assert [r["name"] for r in card.card_model(rep)["rows"]] == ["Claude Code", "Codex CLI"]


def test_same_agent_twice_shows_the_model():
    rep = rep_of(
        entry("a", "mock", "mock-steady", 40, 50, simulated=True),
        entry("b", "mock", "mock-flaky", 30, 50, simulated=True),
        entry("c", "claude", "sonnet", 20, 50),
        entry("d", "claude", "opus", 25, 50),
    )
    names = [r["name"] for r in card.card_model(rep)["rows"]]
    assert names == ["Claude Code opus", "Claude Code sonnet", "mock-flaky", "mock-steady"]


def parse(svg: str) -> ET.Element:
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"
    assert (root.get("width"), root.get("height"), root.get("viewBox")) == (
        "1200",
        "630",
        "0 0 1200 630",
    )
    return root


def texts(root: ET.Element) -> list[str]:
    return [t.text or "" for t in root.iter(f"{SVG_NS}text")]


def test_svg_is_valid_and_self_contained():
    rep = rep_of(entry("a", "claude", "opus <&> x", 30, 30), entry("b", "codex", "gpt", 28, 30))
    svg = card.to_svg(rep)
    root = parse(svg)
    t = texts(root)
    assert "measured with rerun-bench" in t and card.COMMAND in t and card.REPO in t
    assert "opus <&> x" in t  # escaped in the file, intact after parsing
    assert root.find(f"{SVG_NS}title").text.startswith("The 95% intervals")
    assert "@media (prefers-color-scheme: dark)" in svg
    for bad in ("<script", "<image", "href=", "url(", "@import"):
        assert bad not in svg
    for d in DASHES:
        assert d not in svg


def test_simulated_results_are_labeled():
    sim = card.to_svg(rep_of(entry("a", "mock", "mock", 20, 30, simulated=True)))
    t = texts(parse(sim))
    assert "SIMULATED" in t
    assert any("simulated" in x for x in t)
    real = card.to_svg(rep_of(entry("a", "claude", "opus", 20, 30)))
    assert "simulated" not in real.lower()


def test_interval_whiskers_are_drawn_on_the_axis():
    rep = rep_of(entry("a", "codex", "gpt", 28, 30))
    root = parse(card.to_svg(rep))
    lo, hi = wilson_interval(28, 30)
    scale = card.CHART_R - card.CHART_L
    paths = [p.get("d") for p in root.iter(f"{SVG_NS}path")]
    whisker = next(d for d in paths if d.startswith(f"M{card._n(card.CHART_L + lo * scale)} "))
    assert f"H{card._n(card.CHART_L + hi * scale)}" in whisker


def test_pilot_card_is_up_to_date():
    committed = (PILOT / "card.svg").read_text(encoding="utf-8")
    # The pilot's raw results are not in the repository; its JSON report is.
    rep = card.from_report_json(json.loads((PILOT / "report.json").read_text(encoding="utf-8")))
    assert card.to_svg(rep) == committed, (
        "regenerate with: uv run rerun-bench card docs/pilot-2026-10-03/report.json "
        "-o docs/pilot-2026-10-03/card.svg"
    )
    if (PILOT / "results").is_dir():  # a local checkout that has them gives the same card
        assert card.to_svg(report.build(PILOT / "results")) == committed
    t = texts(parse(committed))
    assert "Claude Code" in t and "Codex CLI" in t and "SIMULATED" not in t
    assert "pass^3" in t


def test_card_from_a_saved_json_report(tmp_path, capsys):
    target = tmp_path / "c.svg"
    assert run_cli("card", str(PILOT / "report.json"), "-o", str(target)) == 0
    assert target.read_text(encoding="utf-8") == (PILOT / "card.svg").read_text(encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    capsys.readouterr()
    assert run_cli("card", str(bad), "-o", str(target)) == 2
    assert "not a rerun-bench JSON report" in capsys.readouterr().err


def run_cli(*args):
    return cli.main(["--tasks-dir", str(TASKS_DIR), *args])


def test_card_command_on_mock_runs(tmp_path, capsys):
    out = tmp_path / "results"
    for model, prob in (("mock-steady", "0.85"), ("mock-flaky", "0.6")):
        args = ["run", "--agent", "mock", "--model", model, "--agent-opt", f"pass_prob={prob}"]
        args += ["--runs", "3", "--out", str(out), "--run-id", model, "--quiet", "--no-report"]
        assert run_cli(*args) == 0
    capsys.readouterr()
    target = tmp_path / "card.svg"
    assert run_cli("card", str(out), "-o", str(target)) == 0
    printed = capsys.readouterr().out
    assert f"wrote {target} (1200x630 SVG)" in printed
    assert "rsvg-convert -o" in printed
    t = texts(parse(target.read_text(encoding="utf-8")))
    assert "SIMULATED" in t and "mock-flaky" in t and "mock-steady" in t
    assert_no_winner(" ".join(t))


@pytest.mark.parametrize(
    ("name", "message"),
    [("card.png", "PNG output is not built in"), ("card.txt", "-o must end in .svg")],
)
def test_card_command_rejects_other_formats(tmp_path, capsys, name, message):
    assert run_cli("card", str(PILOT / "report.json"), "-o", str(tmp_path / name)) == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / name).exists()


def test_card_command_errors(tmp_path, capsys):
    assert run_cli("card", str(tmp_path / "missing")) == 2
    assert "does not exist" in capsys.readouterr().err
    assert run_cli("card", str(tmp_path), "-o", str(tmp_path / "c.svg")) == 2
    assert "no runs found" in capsys.readouterr().err
    assert run_cli("card", str(PILOT / "report.json"), "--k", "0") == 2
