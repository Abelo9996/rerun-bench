"""Install-plan selection (pure: decided from files in the repo root, no install run)."""

from __future__ import annotations

from rerun_bench import envs


def test_python_plan_prefers_test_extra_then_plain(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\n[project.optional-dependencies]\n"
        "test=['pytest-cov']\ndocs=['sphinx']\n",
        encoding="utf-8",
    )
    plan = envs.python_install_plan(tmp_path)
    assert plan[0] == ["uv", "pip", "install", ".[test]"]
    assert ["uv", "pip", "install", "."] in plan
    # Never editable: an editable finder would shadow the per-commit worktree source.
    assert all("-e" not in cmd for cmd in plan)


def test_python_plan_uses_requirements_files(tmp_path):
    (tmp_path / "setup.py").write_text("from setuptools import setup; setup()", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    plan = envs.python_install_plan(tmp_path)
    assert ["uv", "pip", "install", "-r", "requirements-dev.txt"] in plan
    assert ["uv", "pip", "install", "."] in plan


def test_python_plan_flat_layout_has_nothing_to_install(tmp_path):
    # No pyproject/setup and no requirements: pytest alone (added by prepare_env) suffices.
    assert envs.python_install_plan(tmp_path) == []


def test_python_plan_dev_extra_when_no_test_extra(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\n[project.optional-dependencies]\ndev=['pytest']\n",
        encoding="utf-8",
    )
    plan = envs.python_install_plan(tmp_path)
    assert plan[0] == ["uv", "pip", "install", ".[dev]"]


def test_js_plan_ci_with_lockfile_else_install(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert envs.js_install_plan(tmp_path) == [["npm", "install"]]
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    plan = envs.js_install_plan(tmp_path)
    assert plan[0] == ["npm", "ci"] and ["npm", "install"] in plan


def test_prepare_env_unknown_language_is_a_noop(tmp_path):
    env = envs.prepare_env(tmp_path, "go", tmp_path, tmp_path)
    assert env.language == "go" and env.ok and env.python is None
