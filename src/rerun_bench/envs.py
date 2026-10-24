"""Prepare an isolated dependency environment per mined repository, cached across worktrees.

Most real repositories have third-party test dependencies, so mining and replaying them means
installing those dependencies somewhere the test can import them. This module builds one
environment per repository (a uv virtualenv for Python, an ``npm`` install for JavaScript) and
reuses it for every worktree of that repository: the install runs once, not once per commit.

The install-plan selection (which commands to try, in order) is a pure function of the files in
the repository root, so it is unit-testable without running an install.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .runners import resolve_exe

# Extras names, in preference order, that usually carry test dependencies.
TEST_EXTRAS = ("test", "tests", "testing", "dev", "develop")
# Requirements files, in preference order, that usually carry test dependencies.
REQ_FILES = (
    "requirements-test.txt",
    "requirements_test.txt",
    "requirements-dev.txt",
    "requirements_dev.txt",
    "test-requirements.txt",
    "requirements/test.txt",
    "requirements/dev.txt",
    "requirements.txt",
)


@dataclass
class PreparedEnv:
    """A dependency environment for one repository, shared by all its worktrees."""

    language: str
    python: str | None = None  # interpreter that can import the repo's test deps
    node_modules: str | None = None  # a populated node_modules to link into worktrees
    install_cmd: list[str] | None = None
    install_seconds: float | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _read_extras(repo_root: Path) -> list[str]:
    path = repo_root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    extras = (data.get("project") or {}).get("optional-dependencies") or {}
    return [e for e in TEST_EXTRAS if e in extras]


def python_install_plan(repo_root: Path) -> list[list[str]]:
    """Ordered ``uv pip install`` commands to try for a Python repo; stop at the first success.

    A packaged project is installed (preferring a test/dev extra so plugins and test helpers come
    along); a requirements file is used when present. The install is non-editable on purpose: the
    source under test is the per-commit worktree, put on ``PYTHONPATH`` so it shadows the copy in
    site-packages. An editable (PEP 660) install registers a meta-path finder that would instead
    win over ``PYTHONPATH`` and make every commit import the same source. ``pytest`` is ensured
    separately by :func:`prepare_env`, so a repo with no declared test deps still runs.
    """
    plan: list[list[str]] = []
    packaged = (repo_root / "pyproject.toml").is_file() or (repo_root / "setup.py").is_file()
    if packaged:
        for extra in _read_extras(repo_root):
            plan.append(["uv", "pip", "install", f".[{extra}]"])
    for req in REQ_FILES:
        if (repo_root / req).is_file():
            plan.append(["uv", "pip", "install", "-r", req])
    if packaged:
        plan.append(["uv", "pip", "install", "."])
    # Deduplicate while preserving order.
    seen: set[tuple[str, ...]] = set()
    out = []
    for cmd in plan:
        key = tuple(cmd)
        if key not in seen:
            seen.add(key)
            out.append(cmd)
    return out


def js_install_plan(repo_root: Path) -> list[list[str]]:
    """``npm ci`` when a lockfile is present (reproducible), otherwise ``npm install``."""
    if (repo_root / "package-lock.json").is_file() or (repo_root / "npm-shrinkwrap.json").is_file():
        return [["npm", "ci"], ["npm", "install"]]
    return [["npm", "install"]]


# ---- running the plans -----------------------------------------------------------------


def prepare_env(repo: Path, language: str, base: Path, cache_root: Path) -> PreparedEnv:
    """Build the environment for ``language`` once, under ``cache_root``.

    ``base`` is a stable checkout to install from (a worktree the caller keeps alive), so an
    editable install's metadata is never written into the user's own checkout. The returned
    :class:`PreparedEnv` records the install command and time, or an exact error on failure.
    """
    if language == "python":
        return _prepare_python(base, cache_root)
    if language == "javascript":
        return _prepare_js(base, cache_root)
    # go and rust resolve dependencies through their own module caches on first build.
    return PreparedEnv(language)


def _prepare_python(base: Path, cache_root: Path) -> PreparedEnv:
    env = PreparedEnv("python")
    venv = cache_root / "venv"
    proc = subprocess.run(["uv", "venv", str(venv)], capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        env.error = f"uv venv failed: {proc.stderr.strip()[-300:]}"
        return env
    python = (
        venv
        / ("Scripts" if os.name == "nt" else "bin")
        / ("python.exe" if os.name == "nt" else "python")
    )
    env.python = str(python)
    t0 = time.perf_counter()
    last = "no install command applied"
    for cmd in python_install_plan(base):
        full = [*cmd, "--python", str(python)]
        proc = subprocess.run(full, cwd=base, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            env.install_cmd = cmd
            break
        last = (proc.stderr or proc.stdout).strip()[-300:]
    else:
        if (base / "pyproject.toml").is_file() or (base / "setup.py").is_file():
            env.error = f"could not install the project: {last}"
            return env
    # Ensure pytest exists even when the repo declares no test dependency.
    pt = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "pytest"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if pt.returncode != 0 and not _has_pytest(python):
        env.error = f"could not install pytest: {pt.stderr.strip()[-200:]}"
        return env
    env.install_seconds = round(time.perf_counter() - t0, 2)
    return env


def _has_pytest(python: Path) -> bool:
    return subprocess.run([str(python), "-c", "import pytest"], capture_output=True).returncode == 0


def _prepare_js(base: Path, cache_root: Path) -> PreparedEnv:
    env = PreparedEnv("javascript")
    t0 = time.perf_counter()
    last = "npm not run"
    for cmd in js_install_plan(base):
        # On Windows, npm is a .cmd shim that a bare name does not resolve to.
        full = [resolve_exe(cmd[0]), *cmd[1:]]
        proc = subprocess.run(full, cwd=base, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            env.install_cmd = cmd
            env.node_modules = str(base / "node_modules")
            env.install_seconds = round(time.perf_counter() - t0, 2)
            return env
        last = (proc.stderr or proc.stdout).strip()[-300:]
    env.error = f"npm install failed: {last}"
    return env


def link_node_modules(node_modules: str | None, worktree: Path) -> None:
    """Make a prepared node_modules importable from ``worktree`` via a symlink."""
    if not node_modules:
        return
    target = worktree / "node_modules"
    if target.exists() or target.is_symlink():
        return
    try:
        target.symlink_to(node_modules)
    except OSError:
        # Fall back to a copy only if the tree is small; otherwise leave it to NODE_PATH.
        src = Path(node_modules)
        if src.is_dir() and sum(1 for _ in src.rglob("*")) < 20000:
            shutil.copytree(src, target, symlinks=True)
