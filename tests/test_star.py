"""The one-time star prompt: shown once per machine, never in CI, pipes, JSON or on opt-out."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rerun_bench import cli, star

from .conftest import TASKS_DIR


@pytest.fixture
def interactive(monkeypatch):
    """A terminal session outside CI with no opt-out set."""
    for name in star.CI_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(star.OPT_OUT_ENV, raising=False)
    monkeypatch.setattr(star, "_interactive", lambda: True)


@pytest.fixture
def results(tmp_path):
    out = tmp_path / "results"
    args = ["--tasks-dir", str(TASKS_DIR), "run", "--agent", "mock", "--tasks", "edit-config"]
    args += ["--runs", "2", "--out", str(out), "--run-id", "m", "--quiet", "--no-report"]
    assert cli.main(args) == 0
    return out


def report(results, *extra):
    return cli.main(["report", str(results), *extra])


def test_shown_once_then_never(interactive, results, capsys):
    capsys.readouterr()
    assert report(results, "--format", "md") == 0
    first = capsys.readouterr()
    assert star.MESSAGE in first.err
    assert star.MESSAGE not in first.out, "the prompt never goes to stdout"
    assert first.err.count(star.MESSAGE) == 1
    assert (star.state_dir() / star.MARKER).is_file()

    for _ in range(3):
        assert report(results, "--format", "md") == 0
        assert star.MESSAGE not in capsys.readouterr().err


def test_shown_after_run_summary_then_not_after_report(interactive, tmp_path, capsys):
    out = tmp_path / "r"
    argv = ["--tasks-dir", str(TASKS_DIR), "run", "--agent", "mock", "--tasks", "edit-config"]
    assert cli.main([*argv, "--runs", "2", "--out", str(out), "--run-id", "a"]) == 0
    assert star.MESSAGE in capsys.readouterr().err
    assert report(out) == 0
    assert star.MESSAGE not in capsys.readouterr().err


def test_not_shown_for_quiet_or_no_report_runs(interactive, tmp_path, capsys):
    argv = ["--tasks-dir", str(TASKS_DIR), "run", "--agent", "mock", "--tasks", "edit-config"]
    argv += ["--runs", "1", "--out", str(tmp_path)]
    assert cli.main([*argv, "--run-id", "q", "--quiet"]) == 0
    assert cli.main([*argv, "--run-id", "n", "--no-report"]) == 0
    assert star.MESSAGE not in capsys.readouterr().err
    assert not (star.state_dir() / star.MARKER).exists()


def test_not_shown_for_json(interactive, results, capsys):
    assert report(results, "--format", "json") == 0
    captured = capsys.readouterr()
    json.loads(captured.out)
    assert star.MESSAGE not in captured.err
    assert not (star.state_dir() / star.MARKER).exists(), "a JSON report does not use it up"


def test_not_shown_after_failed_report(interactive, tmp_path, capsys):
    assert report(tmp_path / "missing") == 2
    assert star.MESSAGE not in capsys.readouterr().err


@pytest.mark.parametrize(
    "name,value", [("CI", "true"), ("GITHUB_ACTIONS", "true"), ("GITLAB_CI", "1"), ("CI", "1")]
)
def test_suppressed_in_ci(interactive, results, monkeypatch, capsys, name, value):
    monkeypatch.setenv(name, value)
    assert report(results, "--format", "md") == 0
    assert star.MESSAGE not in capsys.readouterr().err
    assert not (star.state_dir() / star.MARKER).exists()


def test_ci_false_is_not_ci(monkeypatch):
    assert not star.in_ci({"CI": "false"})
    assert not star.in_ci({"CI": "0"})
    assert not star.in_ci({})
    assert star.in_ci({"CI": "true"})
    assert star.in_ci({"JENKINS_URL": "https://ci.example.com/"})


@pytest.mark.parametrize("value", ["1", "true", "yes"])
def test_suppressed_by_env(interactive, results, monkeypatch, capsys, value):
    monkeypatch.setenv(star.OPT_OUT_ENV, value)
    assert report(results, "--format", "md") == 0
    assert star.MESSAGE not in capsys.readouterr().err
    assert not (star.state_dir() / star.MARKER).exists()


def test_suppressed_when_piped(results, monkeypatch, capsys):
    for name in star.CI_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(star.OPT_OUT_ENV, raising=False)
    # capsys replaces stdout and stderr with non-terminal streams, like a pipe.
    assert not star._interactive()
    assert report(results, "--format", "md") == 0
    assert star.MESSAGE not in capsys.readouterr().err
    assert not (star.state_dir() / star.MARKER).exists()


def test_interactive_needs_both_streams_to_be_terminals(monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.setattr(sys, "stderr", Tty())
    assert star._interactive()
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert not star._interactive(), "stdout piped"
    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    assert not star._interactive(), "stderr redirected"


def test_not_shown_if_marker_cannot_be_written(interactive, results, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv(star.STATE_DIR_ENV, str(blocker / "sub"))
    assert report(results, "--format", "md") == 0
    assert star.MESSAGE not in capsys.readouterr().err, "never risk showing it twice"


def test_state_dir_layout(monkeypatch):
    monkeypatch.delenv(star.STATE_DIR_ENV, raising=False)
    path = star.state_dir()
    assert path.name == "rerun-bench"
    if sys.platform == "darwin":
        assert path.parent == Path.home() / "Library" / "Application Support"
    elif sys.platform != "win32":
        monkeypatch.setenv("XDG_STATE_HOME", "/xdg/state")
        assert star.state_dir() == Path("/xdg/state/rerun-bench")


@pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX pseudo-terminal")
def test_real_terminal_end_to_end(results, tmp_path):
    """Run the CLI in a pseudo-terminal, as a person would: shown the first time only."""
    import pty

    env = {k: v for k, v in os.environ.items() if k not in star.CI_ENV_VARS}
    env.pop(star.OPT_OUT_ENV, None)
    env[star.STATE_DIR_ENV] = str(tmp_path / "state")

    def run_in_pty() -> str:
        primary, secondary = pty.openpty()
        proc = subprocess.Popen(
            [sys.executable, "-m", "rerun_bench", "report", str(results), "--format", "md"],
            stdin=secondary,
            stdout=secondary,
            stderr=secondary,
            env=env,
            close_fds=True,
        )
        os.close(secondary)
        chunks = []
        while True:
            try:
                data = os.read(primary, 4096)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        os.close(primary)
        assert proc.wait(timeout=60) == 0
        return b"".join(chunks).decode("utf-8", "replace")

    assert star.MESSAGE in run_in_pty()
    assert star.MESSAGE not in run_in_pty()

    piped = subprocess.run(
        [sys.executable, "-m", "rerun_bench", "report", str(results)],
        capture_output=True,
        text=True,
        env={**env, star.STATE_DIR_ENV: str(tmp_path / "state2")},
        check=True,
    )
    assert star.MESSAGE not in piped.stdout + piped.stderr
