"""Every shipped task must fail untouched and pass with its reference solution."""

import pytest

from rerun_bench import tasks as tasks_mod
from rerun_bench import workspace as ws

from .conftest import TASKS_DIR

TASK_IDS = sorted(p.name for p in TASKS_DIR.iterdir() if (p / "task.toml").is_file())


def test_suite_size():
    assert 8 <= len(TASK_IDS) <= 12


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_task_schema(task_id):
    t = tasks_mod.load_task(TASKS_DIR / task_id)
    assert t.id == task_id
    assert t.title and t.prompt and t.timeout > 0 and t.tags
    assert t.solution.is_dir(), "every task needs a reference solution"
    assert not (t.workspace / "verify.py").exists(), "verifier must stay hidden from the agent"


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_untouched_workspace_fails(task_id):
    t = tasks_mod.load_task(TASKS_DIR / task_id)
    work = ws.fresh_copy(t.workspace)
    try:
        res = tasks_mod.verify(t, work)
    finally:
        ws.cleanup(work)
    assert not res.passed, res.output


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_reference_solution_passes(task_id):
    t = tasks_mod.load_task(TASKS_DIR / task_id)
    work = ws.fresh_copy(t.workspace)
    try:
        ws.overlay(t.solution, work)
        res = tasks_mod.verify(t, work)
        res2 = tasks_mod.verify(t, work)
    finally:
        ws.cleanup(work)
    assert res.passed, res.output
    assert res2.passed == res.passed, "verifier must be deterministic"


def test_select(all_tasks):
    assert tasks_mod.select(all_tasks, "all") == all_tasks
    picked = tasks_mod.select(all_tasks, "edit-config,minimal-fix")
    assert [t.id for t in picked] == ["edit-config", "minimal-fix"]
    tagged = tasks_mod.select(all_tasks, "tag:refactor")
    assert {t.id for t in tagged} == {"refactor-extract-helper", "multi-file-rename"}
    with pytest.raises(tasks_mod.TaskError):
        tasks_mod.select(all_tasks, "nope")


def test_load_task_rejects_bad_toml(tmp_path):
    d = tmp_path / "x"
    (d / "workspace").mkdir(parents=True)
    (d / "verify.py").write_text("")
    (d / "task.toml").write_text('id = "y"\ntitle = "t"\nprompt = "p"\ntimeout = 1\n')
    with pytest.raises(tasks_mod.TaskError, match="must match"):
        tasks_mod.load_task(d)
    (d / "task.toml").write_text('id = "x"\ntitle = "t"\n')
    with pytest.raises(tasks_mod.TaskError, match="missing keys"):
        tasks_mod.load_task(d)


def test_over_edit_trap_rejects_cleanup(all_tasks):
    """A correct fix plus an unrequested cleanup must fail minimal-fix."""
    t = next(x for x in all_tasks if x.id == "minimal-fix")
    work = ws.fresh_copy(t.workspace)
    try:
        ws.overlay(t.solution, work)
        p = work / "legacy.py"
        p.write_text(p.read_text().replace("import os, sys\n", "import os\nimport sys\n"))
        assert not tasks_mod.verify(t, work).passed
    finally:
        ws.cleanup(work)


def test_weak_tests_fail_write_tests(all_tasks):
    """Tests that pass but miss injected bugs must not count."""
    t = next(x for x in all_tasks if x.id == "write-tests")
    work = ws.fresh_copy(t.workspace)
    try:
        (work / "tests" / "test_duration.py").write_text(
            "import unittest\nfrom duration import parse_duration\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_one(self):\n        self.assertEqual(parse_duration('45s'), 45)\n"
        )
        res = tasks_mod.verify(t, work)
        assert not res.passed
        assert "did not catch" in res.output
    finally:
        ws.cleanup(work)
