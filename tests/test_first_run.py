"""First-run and unhappy-path behavior: relative task dirs, agent errors, Ctrl-C, reports."""

import json
import shutil
import sys

import pytest

from rerun_bench import cli
from rerun_bench import report as report_mod
from rerun_bench.adapters import ADAPTERS, REAL_AGENTS
from rerun_bench.adapters.base import Adapter, Usage, error_summary
from rerun_bench.adapters.claude import ClaudeAdapter
from rerun_bench.adapters.mock import MockAdapter

from .conftest import TASKS_DIR


def run_cli(*args):
    return cli.main(["--tasks-dir", str(TASKS_DIR), *args])


def _fake_claude(monkeypatch, script: str) -> None:
    """Make the claude adapter run a Python one-liner instead of the real CLI."""
    monkeypatch.setattr(ClaudeAdapter, "available", lambda self: True)
    monkeypatch.setattr(ClaudeAdapter, "version", lambda self: "fake 1.0")
    monkeypatch.setattr(
        ClaudeAdapter, "build_command", lambda self, p, w: [sys.executable, "-c", script]
    )


NOT_LOGGED_IN = (
    "import json, sys; print(json.dumps({'type': 'result', 'is_error': True, "
    "'result': 'Not logged in. Please run /login', 'total_cost_usd': 0})); sys.exit(1)"
)


# ---- task directories ---------------------------------------------------------------------


def test_relative_tasks_dir_works(tmp_path, monkeypatch, capsys):
    """`rerun-bench --tasks-dir tasks verify-tasks` from the repo root, as the README says."""
    shutil.copytree(TASKS_DIR / "edit-config", tmp_path / "tasks" / "edit-config")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--tasks-dir", "tasks", "verify-tasks", "-v"]) == 0
    assert "ok" in capsys.readouterr().out
    out = tmp_path / "results"
    code = cli.main(
        ["--tasks-dir", "tasks", "run", "--agent", "mock", "--runs", "3", "--out", str(out)]
        + ["--agent-opt", "pass_prob=1", "--run-id", "r", "--quiet", "--no-report"]
    )
    assert code == 0
    rows = [json.loads(x) for x in (out / "r" / "runs.jsonl").read_text().splitlines()]
    assert all(r["passed"] for r in rows), "the verifier must be found from any cwd"


def test_missing_or_empty_tasks_dir_is_a_clear_error(tmp_path, capsys):
    assert cli.main(["--tasks-dir", str(tmp_path / "nope"), "list"]) == 2
    assert "does not exist" in capsys.readouterr().err
    assert cli.main(["--tasks-dir", str(tmp_path), "list"]) == 2
    assert "no tasks in" in capsys.readouterr().err
    assert run_cli("verify-tasks", "--tasks", "nope") == 2
    assert "unknown task" in capsys.readouterr().err


# ---- the cost gate ----------------------------------------------------------------------


def test_every_non_mock_adapter_needs_yes(tmp_path, monkeypatch, capsys):
    assert REAL_AGENTS == {n for n in ADAPTERS if n != "mock"}

    class NewAgent(Adapter):
        name = "newagent"
        binary = "newagent"

        def build_command(self, prompt, workspace):
            return [self.binary, prompt]

        def parse_output(self, stdout, stderr):
            return Usage()

    monkeypatch.setitem(ADAPTERS, "newagent", NewAgent)
    monkeypatch.setattr(NewAgent, "available", lambda self: True)
    code = run_cli("run", "--agent", "newagent", "--runs", "1", "--out", str(tmp_path))
    assert code == 3 and not any(tmp_path.iterdir())
    monkeypatch.setattr(NewAgent, "available", lambda self: False)
    code = run_cli("run", "--agent", "newagent", "--runs", "1", "--out", str(tmp_path), "--yes")
    assert code == 2 and "--agent-opt bin=" in capsys.readouterr().err


def test_cost_gate_message_says_how_many_runs_and_roughly_what_it_costs(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(ClaudeAdapter, "available", lambda self: True)
    assert run_cli("run", "--agent", "claude", "--runs", "2", "--out", str(tmp_path)) == 3
    err = capsys.readouterr().err
    n = 2 * len(list(p for p in TASKS_DIR.iterdir() if (p / "task.toml").is_file()))
    assert f"{n} runs of the real `claude` CLI" in err
    assert "tokens" in err and "$" in err and "--yes" in err
    assert all(len(line) <= 80 for line in err.splitlines() if "`claude`" not in line)


# ---- agent errors -----------------------------------------------------------------------


def test_error_summary_finds_the_agent_message():
    claude = json.dumps({"type": "result", "is_error": True, "result": "Credit balance too low"})
    assert error_summary(claude, "") == "Credit balance too low"
    codex = "\n".join(
        [
            json.dumps({"type": "error", "message": "Reconnecting... 1/5"}),
            json.dumps({"type": "turn.failed", "error": {"message": "usage limit reached"}}),
        ]
    )
    assert error_summary(codex, "") == "usage limit reached"
    assert error_summary("", "warn\nError: not authenticated\n") == "Error: not authenticated"
    assert error_summary("", "") == "no output"
    assert len(error_summary("x" * 500, "")) == 160


def test_login_failure_stops_early_and_resume_reruns(tmp_path, monkeypatch, capsys):
    _fake_claude(monkeypatch, NOT_LOGGED_IN)
    args = ["run", "--agent", "claude", "--tasks", "all", "--runs", "2", "--out", str(tmp_path)]
    args += ["--run-id", "c", "--yes", "--no-report"]
    assert run_cli(*args) == 4
    io = capsys.readouterr()
    assert "agent error: exit code 1: Not logged in" in io.out
    assert "stopped: 3 runs in a row ended in an agent error" in io.err
    assert "--run-id c" in io.err and "--resume" in io.err
    d = tmp_path / "c"
    assert (d / "runs.jsonl").read_text() == "", "setup failures are not scored"
    assert len((d / "errors.jsonl").read_text().splitlines()) == 3
    assert json.loads((d / "meta.json").read_text())["stopped"]

    # Fixed: resume runs everything, including the three set aside.
    _fake_claude(monkeypatch, "print('{}')")
    assert run_cli(*args, "--resume") == 0
    rows = (d / "runs.jsonl").read_text().splitlines()
    n_tasks = sum(1 for p in TASKS_DIR.iterdir() if (p / "task.toml").is_file())
    assert len(rows) == 2 * n_tasks
    assert "stopped" not in json.loads((d / "meta.json").read_text())


def test_agent_errors_are_counted_and_shown(tmp_path, monkeypatch, capsys):
    _fake_claude(monkeypatch, NOT_LOGGED_IN)
    args = ["run", "--agent", "claude", "--tasks", "edit-config,minimal-fix", "--runs", "2"]
    args += ["--out", str(tmp_path), "--run-id", "c", "--yes", "--max-consecutive-errors", "0"]
    assert run_cli(*args, "--no-report") == 0
    rows = [json.loads(x) for x in (tmp_path / "c" / "runs.jsonl").read_text().splitlines()]
    assert len(rows) == 4 and all("Not logged in" in r["agent_error"] for r in rows)
    rep = report_mod.build(tmp_path)
    assert rep["entries"][0]["metrics"]["agent_error_runs"] == 4
    for fmt in ("text", "md", "html"):
        out = report_mod.RENDERERS[fmt](rep)
        assert "4 of 4 runs ended in an agent error" in " ".join(out.split()), fmt


# ---- interruption -----------------------------------------------------------------------


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_ctrl_c_prints_resume_command_and_resume_finishes(tmp_path, monkeypatch, capsys, jobs):
    real_run = MockAdapter.run
    calls = []

    def flaky_run(self, *a, **k):
        calls.append(1)
        if len(calls) == 3:
            raise KeyboardInterrupt
        return real_run(self, *a, **k)

    monkeypatch.setattr(MockAdapter, "run", flaky_run)
    args = ["run", "--agent", "mock", "--tasks", "edit-config,minimal-fix", "--runs", "3"]
    args += ["--out", str(tmp_path), "--jobs", jobs]
    assert run_cli(*args, "--no-report") == 130
    err = capsys.readouterr().err
    assert "interrupted" in err and "--resume" in err
    (run_dir,) = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert run_dir.name in err, "the auto-generated run id is printed"
    recorded = len((run_dir / "runs.jsonl").read_text().splitlines())
    assert recorded < 6
    monkeypatch.setattr(MockAdapter, "run", real_run)
    assert run_cli(*args, "--run-id", run_dir.name, "--resume", "--no-report") == 0
    assert len((run_dir / "runs.jsonl").read_text().splitlines()) == 6


def test_resume_count_in_gate_is_remaining_runs(tmp_path, monkeypatch, capsys):
    _fake_claude(monkeypatch, "print('{}')")
    args = ["run", "--agent", "claude", "--tasks", "edit-config", "--out", str(tmp_path)]
    args += ["--run-id", "c", "--no-report"]
    assert run_cli(*args, "--runs", "1", "--yes") == 0
    capsys.readouterr()
    assert run_cli(*args, "--runs", "3", "--resume") == 3
    assert "This starts 2 runs" in capsys.readouterr().err


# ---- reports ----------------------------------------------------------------------------


def _two_mock_runs(tmp_path):
    for rid, p in (("steady", "0.9"), ("flaky", "0.5")):
        args = ["run", "--agent", "mock", "--model", rid, "--agent-opt", f"pass_prob={p}"]
        args += ["--tasks", "all", "--runs", "3", "--out", str(tmp_path), "--run-id", rid]
        assert run_cli(*args, "--quiet", "--no-report") == 0
    return report_mod.build(tmp_path)


def test_text_report_fits_80_columns_and_explains_metrics(tmp_path, capsys):
    rep = _two_mock_runs(tmp_path)
    text = report_mod.to_text(rep)
    long = [ln for ln in text.splitlines() if len(ln) > 80 and not ln.startswith("Definitions")]
    assert not long, long
    assert "all 3 reruns of a task pass" in text and "Comparison" in text
    assert "not a ranking" in text and "(simulated)" in text
    text.encode("ascii")  # Windows consoles


def test_report_never_names_a_winner_when_intervals_overlap(tmp_path):
    rep = _two_mock_runs(tmp_path)
    a, b = rep["entries"]
    a["metrics"]["pass_rate_ci95"], b["metrics"]["pass_rate_ci95"] = [0.5, 0.9], [0.3, 0.6]
    rep["comparison"] = report_mod.compare(rep["entries"])
    assert rep["comparison"][0]["intervals_overlap"]
    for fmt in ("text", "md", "html"):
        out = " ".join(report_mod.RENDERERS[fmt](rep).lower().split())
        assert "not enough to tell the rows apart" in out
        for word in ("winner", "better", "best", "beats"):
            assert word not in out, (fmt, word)
    b["metrics"]["pass_rate_ci95"] = [0.1, 0.4]
    rep["comparison"] = report_mod.compare(rep["entries"])
    assert "intervals do not overlap" in " ".join(report_mod.to_text(rep).split())


def test_html_report_explains_metrics_inline(tmp_path):
    html = report_mod.to_html(_two_mock_runs(tmp_path))
    assert "How to read this" in html and "pass^3" in html
    assert "chance that 3 reruns of the same task all pass" in html
    assert "[" in html and "95%" in html and "not a ranking" in html
    assert "Simulated" in html


def test_report_format_default_and_bad_k(tmp_path, capsys):
    _two_mock_runs(tmp_path)
    capsys.readouterr()
    assert run_cli("report", str(tmp_path)) == 0  # stdout is not a terminal under pytest
    assert capsys.readouterr().out.startswith("# rerun-bench report")
    assert run_cli("report", str(tmp_path), "--format", "text") == 0
    assert capsys.readouterr().out.startswith("rerun-bench report:")
    assert run_cli("report", str(tmp_path), "--k", "0") == 2


def test_incomplete_run_is_flagged(tmp_path, capsys):
    args = ["run", "--agent", "mock", "--tasks", "edit-config", "--runs", "3"]
    args += ["--out", str(tmp_path), "--run-id", "r", "--quiet", "--no-report"]
    assert run_cli(*args) == 0
    runs = tmp_path / "r" / "runs.jsonl"
    runs.write_text("\n".join(runs.read_text().splitlines()[:2]) + "\n")
    text = report_mod.to_text(report_mod.build(tmp_path))
    assert "Incomplete: 2 of 3 planned runs" in " ".join(text.split()) and "--resume" in text
