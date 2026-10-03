from pathlib import Path

import pytest

from rerun_bench import tasks as tasks_mod

REPO = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO / "tasks"


@pytest.fixture(scope="session")
def all_tasks():
    return tasks_mod.discover(TASKS_DIR)
