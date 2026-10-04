"""Task discovery and loading.

A task is a directory ``tasks/<id>/`` containing:

- ``task.toml``  -- id, title, prompt, timeout (seconds), tags
- ``workspace/`` -- the starting files the agent sees
- ``verify.py``  -- exits 0 on pass, non-zero on fail; run with cwd = the agent's workspace
- ``solution/``  -- reference solution, overlaid on ``workspace/`` by the test suite

``verify.py`` lives outside the workspace on purpose: the agent never sees the
hidden checks and cannot edit them.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_KEYS = ("id", "title", "prompt", "timeout")


class TaskError(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    prompt: str
    timeout: int
    tags: tuple[str, ...]
    root: Path
    verify_timeout: int = 60
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def solution(self) -> Path:
        return self.root / "solution"

    @property
    def verifier(self) -> Path:
        return self.root / "verify.py"


@dataclass(frozen=True)
class VerifyResult:
    passed: bool
    exit_code: int | None
    output: str
    timed_out: bool = False


def default_tasks_dir() -> Path:
    """Locate the task suite: env override, then wheel-bundled copy, then repo checkout."""
    env = os.environ.get("RERUN_BENCH_TASKS_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    bundled = here / "_bundled_tasks"
    if bundled.is_dir():
        return bundled
    repo = here.parent.parent / "tasks"
    if repo.is_dir():
        return repo
    raise TaskError("could not locate the task suite; pass --tasks-dir")


def load_task(path: Path) -> Task:
    path = Path(path).expanduser().resolve()
    toml_path = path / "task.toml"
    if not toml_path.is_file():
        raise TaskError(f"{path}: missing task.toml")
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise TaskError(f"{toml_path}: missing keys {missing}")
    if data["id"] != path.name:
        raise TaskError(f"{toml_path}: id {data['id']!r} must match directory name {path.name!r}")
    task = Task(
        id=data["id"],
        title=data["title"],
        prompt=data["prompt"].strip(),
        timeout=int(data["timeout"]),
        tags=tuple(data.get("tags", [])),
        root=path,
        verify_timeout=int(data.get("verify_timeout", 60)),
        extra={k: v for k, v in data.items() if k not in (*REQUIRED_KEYS, "tags")},
    )
    if not task.workspace.is_dir():
        raise TaskError(f"{path}: missing workspace/ directory")
    if not task.verifier.is_file():
        raise TaskError(f"{path}: missing verify.py")
    return task


def discover(tasks_dir: Path | None = None) -> list[Task]:
    # Absolute paths: the verifier runs with cwd set to the agent's workspace, so a relative
    # ``--tasks-dir tasks`` would otherwise point every verifier at a file that is not there.
    root = Path(tasks_dir or default_tasks_dir()).expanduser().resolve()
    if not root.is_dir():
        raise TaskError(f"task directory {root} does not exist")
    out = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "task.toml").is_file():
            out.append(load_task(child))
    if not out:
        raise TaskError(
            f"no tasks in {root}: each task is a subdirectory with a task.toml "
            "(see the README section 'Add a task')"
        )
    return out


def select(tasks: list[Task], spec: str) -> list[Task]:
    """Select tasks by ``all``, comma-separated ids, or ``tag:<name>``."""
    spec = spec.strip()
    if spec in ("", "all"):
        return tasks
    by_id = {t.id: t for t in tasks}
    chosen: list[Task] = []
    for item in (s.strip() for s in spec.split(",") if s.strip()):
        if item.startswith("tag:"):
            tag = item[4:]
            chosen.extend(t for t in tasks if tag in t.tags and t not in chosen)
        elif item in by_id:
            if by_id[item] not in chosen:
                chosen.append(by_id[item])
        else:
            raise TaskError(f"unknown task {item!r}; run `rerun-bench list`")
    return chosen


def verify(task: Task, workspace: Path) -> VerifyResult:
    """Run the task's verifier against ``workspace``. Deterministic, offline, stdlib-only."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
    env["RERUN_BENCH_TASK_DIR"] = str(task.root.resolve())
    try:
        proc = subprocess.run(
            [sys.executable, str(task.verifier.resolve())],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=task.verify_timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return VerifyResult(False, None, out[-4000:], timed_out=True)
    output = (proc.stdout + proc.stderr)[-4000:]
    return VerifyResult(proc.returncode == 0, proc.returncode, output)
