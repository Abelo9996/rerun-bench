"""Mining and task building on a synthetic git repository built inside the test.

These run fully offline. They use ``git`` and run the mined test with the interpreter the
test suite already runs under (which has pytest), so no network or external agent is needed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rerun_bench import mining, taskgen
from rerun_bench import tasks as tasks_mod
from rerun_bench import workspace as ws


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _commit(repo: Path, message: str, files: dict[str, str]) -> str:
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture
def fix_repo(tmp_path):
    """A repo whose newest commit fixes a bug and adds the test that proves it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _commit(
        repo,
        "initial: calculator",
        {
            "calc.py": "def add(a, b):\n    return a + b\n",
            "test_calc.py": (
                "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
            ),
        },
    )
    _commit(
        repo,
        "add subtract (buggy)",
        {"calc.py": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a + b\n"},
    )
    fix = _commit(
        repo,
        "Fix sub to subtract instead of add",
        {
            "calc.py": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
            "test_calc.py": (
                "from calc import add, sub\n\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n\n"
                "def test_sub():\n    assert sub(5, 3) == 2\n"
            ),
        },
    )
    return repo, fix


def test_changed_test_names_python_and_js_and_go():
    py_diff = (
        "@@ -1,3 +1,8 @@ class TestThing:\n"
        "     def test_old(self):\n"
        "-        assert f() == 1\n"
        "+        assert f() == 2\n"
        "+\n"
        "+    def test_new(self):\n"
        "+        assert g() == 3\n"
    )
    assert mining.changed_test_names(py_diff, "python") == ("test_new", "test_old")
    js_diff = "@@ -1 +1,3 @@\n+test('handles empty', () => {\n+  assert.equal(f(''), '')\n+})\n"
    assert mining.changed_test_names(js_diff, "javascript") == ("handles empty",)
    go_diff = "@@ -1 +1,3 @@\n+func TestFoo(t *testing.T) {\n+  if foo() != 1 { t.Fail() }\n+}\n"
    assert mining.changed_test_names(go_diff, "go") == ("TestFoo",)
    # No enclosing test and no test call: nothing to narrow to.
    assert mining.changed_test_names("@@ -1 +1 @@\n+x = 1\n", "python") == ()


def test_find_candidates_picks_the_fix_commit(fix_repo):
    repo, fix = fix_repo
    cands = mining.find_candidates(repo, 10)
    with_runner = [c for c in cands if c.runner.name != "none"]
    assert len(with_runner) == 1
    c = with_runner[0]
    assert c.sha == fix
    assert c.test_files == ["test_calc.py"]
    assert c.source_files == ["calc.py"]
    assert c.runner.name == "pytest"


def test_skip_words_exclude_merges_and_refactors(fix_repo):
    repo, _ = fix_repo
    _commit(
        repo,
        "refactor: tidy calc",
        {
            "calc.py": (
                "# tidy\ndef add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
            ),
            "test_calc.py": (
                "# tidy\nfrom calc import add, sub\n\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n\n"
                "def test_sub():\n    assert sub(5, 3) == 2\n"
            ),
        },
    )
    subjects = {c.subject for c in mining.find_candidates(repo, 10)}
    assert not any(s.startswith("refactor") for s in subjects)


def test_verify_candidate_replays(fix_repo, tmp_path):
    repo, _ = fix_repo
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    c = mining.rank([x for x in mining.find_candidates(repo, 10) if x.runner.name != "none"])[0]
    c = mining.verify_candidate(repo, c, scratch)
    assert c.verified, c.skip_reason
    assert c.test_seconds is not None


def test_build_task_passes_verify_tasks(fix_repo, tmp_path):
    repo, _ = fix_repo
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tasks_dir = tmp_path / "tasks"
    c = mining.rank([x for x in mining.find_candidates(repo, 10) if x.runner.name != "none"])[0]
    c = mining.verify_candidate(repo, c, scratch)
    root = taskgen.build_task(repo, c, tasks_dir)

    task = tasks_mod.load_task(root)
    assert task.id == root.name
    assert "mined" in task.tags

    # The untouched workspace must fail, the reference solution must pass: the same contract
    # verify-tasks checks for hand-written tasks.
    base = ws.fresh_copy(task.workspace)
    sol = ws.fresh_copy(task.workspace)
    try:
        r0 = tasks_mod.verify(task, base)
        ws.overlay(task.solution, sol)
        r1 = tasks_mod.verify(task, sol)
    finally:
        ws.cleanup(base)
        ws.cleanup(sol)
    assert not r0.passed, r0.output
    assert r1.passed, r1.output


def test_build_task_hidden_tests_not_in_workspace(fix_repo, tmp_path):
    repo, _ = fix_repo
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tasks_dir = tmp_path / "tasks"
    c = mining.rank([x for x in mining.find_candidates(repo, 10) if x.runner.name != "none"])[0]
    c = mining.verify_candidate(repo, c, scratch)
    root = taskgen.build_task(repo, c, tasks_dir, hide_tests=True)
    # The agent does not see the new assertion; the verifier supplies the real test and the
    # reference solution still passes it.
    ws_test = root / "workspace" / "test_calc.py"
    assert not ws_test.exists() or "test_sub" not in ws_test.read_text(encoding="utf-8")
    task = tasks_mod.load_task(root)
    sol = ws.fresh_copy(task.workspace)
    try:
        ws.overlay(task.solution, sol)
        r1 = tasks_mod.verify(task, sol)
    finally:
        ws.cleanup(sol)
    assert r1.passed, r1.output


def test_guard_rejects_editing_the_test(fix_repo, tmp_path):
    repo, _ = fix_repo
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tasks_dir = tmp_path / "tasks"
    c = mining.rank([x for x in mining.find_candidates(repo, 10) if x.runner.name != "none"])[0]
    c = mining.verify_candidate(repo, c, scratch)
    task = tasks_mod.load_task(taskgen.build_task(repo, c, tasks_dir))
    cheat = ws.fresh_copy(task.workspace)
    try:
        # Make the test trivially pass by gutting it; the guard must catch the edit.
        (cheat / "test_calc.py").write_text("def test_sub():\n    assert True\n", encoding="utf-8")
        r = tasks_mod.verify(task, cheat)
    finally:
        ws.cleanup(cheat)
    assert not r.passed
    assert "modified" in r.output
