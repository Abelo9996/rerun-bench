"""End-to-end through the CLI with the mock adapter (free, offline, deterministic)."""

import json
import re

import pytest

from rerunbench import cli
from rerunbench.adapters.claude import ClaudeAdapter

from .conftest import TASKS_DIR


def run_cli(*args):
    return cli.main(["--tasks-dir", str(TASKS_DIR), *args])


def test_list(capsys):
    assert run_cli("list") == 0
    out = capsys.readouterr().out
    assert "fix-failing-test" in out and "10 tasks" in out


def test_help_runs():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


def test_mock_run_and_reports(tmp_path, capsys):
    out = tmp_path / "results"
    assert (
        run_cli(
            "run",
            "--agent",
            "mock",
            "--tasks",
            "all",
            "--runs",
            "3",
            "--out",
            str(out),
            "--run-id",
            "a",
            "--quiet",
        )
        == 0
    )
    assert (
        run_cli(
            "run",
            "--agent",
            "mock",
            "--model",
            "weak",
            "--agent-opt",
            "pass_prob=0.3",
            "--tasks",
            "tag:refactor,edit-config",
            "--runs",
            "4",
            "--out",
            str(out),
            "--run-id",
            "b",
            "--quiet",
            "--jobs",
            "3",
            "--no-report",
        )
        == 0
    )
    capsys.readouterr()

    runs = [json.loads(x) for x in (out / "a" / "runs.jsonl").read_text().splitlines()]
    assert len(runs) == 30
    meta = json.loads((out / "a" / "meta.json").read_text())
    assert meta["agent"] == "mock" and meta["runs_per_task"] == 3 and meta["cli_version"]
    for r in runs:
        assert (out / "a" / r["diff_path"]).is_file()
        if r["passed"]:
            assert r["lines_added"] + r["lines_removed"] > 0
    # Interleaved order: run 0 of every task precedes any run 1.
    assert [r["run_index"] for r in runs[:10]] == [0] * 10

    assert run_cli("report", str(out), "--format", "json", "-o", str(tmp_path / "r.json")) == 0
    rep = json.loads((tmp_path / "r.json").read_text())
    assert {e["run_id"] for e in rep["entries"]} == {"a", "b"}
    b = next(e for e in rep["entries"] if e["run_id"] == "b")
    assert b["metrics"]["n_tasks"] == 3 and b["metrics"]["k"] == 4

    assert run_cli("report", str(out), "--format", "md") == 0
    md = capsys.readouterr().out
    assert "## Leaderboard" in md and "mock / weak" in md and "edit-config" in md

    html_path = tmp_path / "r.html"
    assert run_cli("report", str(out), "--format", "html", "-o", str(html_path)) == 0
    html = html_path.read_text()
    assert html.startswith("<!doctype html>") and "<style>" in html and "<script>" in html
    assert not re.search(r"(src|href)=[\"']?(https?:)?//", html), "report must be self-contained"
    assert "leaderboard" in html and "minimal-fix" in html


def test_mock_run_is_reproducible(tmp_path, capsys):
    for rid in ("x", "y"):
        run_cli(
            "run",
            "--agent",
            "mock",
            "--tasks",
            "edit-config,minimal-fix",
            "--runs",
            "4",
            "--out",
            str(tmp_path),
            "--run-id",
            rid,
            "--quiet",
            "--no-report",
            "--seed",
            "7",
        )
    capsys.readouterr()

    def key(rid):
        rows = [json.loads(x) for x in (tmp_path / rid / "runs.jsonl").read_text().splitlines()]
        return [(r["task_id"], r["run_index"], r["passed"], r["cost_usd"]) for r in rows]

    assert key("x") == key("y")


def test_real_agent_requires_yes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ClaudeAdapter, "available", lambda self: True)
    called = []
    monkeypatch.setattr(ClaudeAdapter, "run", lambda *a, **k: called.append(1))
    code = run_cli("run", "--agent", "claude", "--runs", "1", "--out", str(tmp_path))
    assert code == 3 and not called
    assert "--yes" in capsys.readouterr().err


def test_errors(tmp_path, capsys):
    assert run_cli("run", "--agent", "mock", "--tasks", "nope", "--out", str(tmp_path)) == 2
    assert run_cli("report", str(tmp_path / "missing")) == 2
    assert run_cli("report", str(tmp_path)) == 2


def test_verify_tasks_command(capsys):
    assert run_cli("verify-tasks", "--tasks", "edit-config") == 0
    assert "ok" in capsys.readouterr().out
