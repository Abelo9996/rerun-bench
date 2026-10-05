from pathlib import Path

import pytest

from rerun_bench import tasks as tasks_mod

REPO = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO / "tasks"


@pytest.fixture(scope="session")
def all_tasks():
    return tasks_mod.discover(TASKS_DIR)


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path_factory, monkeypatch):
    """Keep every test away from the real per-user state directory."""
    monkeypatch.setenv("RERUN_BENCH_STATE_DIR", str(tmp_path_factory.mktemp("state")))
