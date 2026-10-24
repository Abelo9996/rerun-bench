"""Turn a verified fix commit into a task directory the ``run`` pipeline can use.

The task that comes out has the same shape as a hand-written one (``task.toml``,
``workspace/``, ``verify.py``, ``solution/``) plus a ``check.json`` and a ``tests_locked/``
copy of the commit's test files. ``verify.py`` is generated and self-contained: it depends
only on the standard library so it runs under the same interpreter as the rest of the suite.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

from .mining import Candidate, MineError, file_at
from .runners import Runner

TASK_TIMEOUT = 600
VERIFY_TIMEOUT = 180


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "fix"


def task_id(cand: Candidate) -> str:
    return f"{slugify(cand.subject)}-{cand.short[:8]}"


def _export_tree(repo: Path, sha: str, dest: Path) -> None:
    """Extract the full tree at ``sha`` into ``dest`` (no .git), via ``git archive``."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", sha],
        capture_output=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise MineError(f"git archive {sha[:10]} failed: {proc.stderr.decode('utf-8', 'replace')}")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        _safe_extract(tar, dest)


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    base = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(base)):
            raise MineError(f"archive member escapes the task directory: {member.name}")
    try:
        tar.extractall(dest, filter="data")
    except TypeError:  # the filter argument predates Python 3.12
        tar.extractall(dest)  # noqa: S202 - members validated above


def _prompt(cand: Candidate, hide_tests: bool, cmd_human: str) -> str:
    subject = cand.subject.strip()
    body = cand.body.strip()
    lines = [subject] if subject else ["Fix the failing test in this repository."]
    if body and len(body) < 600 and "Signed-off-by" not in body:
        lines.append("")
        lines.append(body)
    lines.append("")
    if hide_tests:
        lines.append(
            "A hidden test checks this fix. Change the source code so the project's tests "
            "pass. The command used to check is:"
        )
    else:
        lines.append(
            "A test in this repository fails. Change the source code so it passes. Run it with:"
        )
    lines.append(f"  {cmd_human}")
    if not hide_tests and cand.test_files:
        quoted = ", ".join(cand.test_files)
        lines.append("")
        lines.append(f"Do not edit the test file(s): {quoted}. Only change the source.")
    return "\n".join(lines).strip()


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _toml_str_array(items: list[str]) -> str:
    return "[" + ", ".join('"' + _toml_escape(i) + '"' for i in items) + "]"


def _write_toml(path: Path, cand: Candidate, tid: str, prompt: str, hide_tests: bool) -> None:
    tags = list(dict.fromkeys(["mined", cand.runner.language, cand.runner.name]))
    prompt_block = prompt.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    seconds = cand.test_seconds if cand.test_seconds is not None else 0
    lines = [
        f'id = "{tid}"',
        f'title = "{_toml_escape(cand.subject.strip()[:80] or tid)}"',
        'prompt = """',
        prompt_block,
        '"""',
        f"timeout = {TASK_TIMEOUT}",
        f"verify_timeout = {VERIFY_TIMEOUT}",
        f"tags = {_toml_str_array(tags)}",
        "",
        "[mined]",
        f'commit = "{cand.sha}"',
        f'parent = "{cand.parent}"',
        f'runner = "{cand.runner.name}"',
        f"hide_tests = {'true' if hide_tests else 'false'}",
        f"test_seconds = {seconds}",
        f"source_files = {_toml_str_array(cand.source_files)}",
        f"test_files = {_toml_str_array(cand.test_files)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


VERIFY_TEMPLATE = '''\
"""Generated hidden check for a mined task. Runs with cwd = the agent's workspace."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(os.environ["RERUN_BENCH_TASK_DIR"])
CFG = json.loads((TASK_DIR / "check.json").read_text(encoding="utf-8"))
WS = Path.cwd()


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


locked = TASK_DIR / "tests_locked"
for rel in CFG["test_files"]:
    src = locked / rel
    dst = WS / rel
    if CFG["hide_tests"]:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    else:
        if not dst.is_file():
            fail(f"test file {rel} is missing from the workspace")
        if dst.read_bytes() != src.read_bytes():
            fail(f"test file {rel} was modified; the task forbids editing the test")

cmd = list(CFG["test_cmd"])
if cmd and cmd[0] == "python":
    interp = CFG.get("python")
    cmd = [interp if interp and Path(interp).exists() else sys.executable] + cmd[1:]

env = dict(os.environ)
paths = [str(WS)]
if (WS / "src").is_dir():
    paths.append(str(WS / "src"))
if env.get("PYTHONPATH"):
    paths.append(env["PYTHONPATH"])
env["PYTHONPATH"] = os.pathsep.join(paths)
env["PYTHONDONTWRITEBYTECODE"] = "1"

node_modules = CFG.get("node_modules")
if node_modules and Path(node_modules).exists():
    link = WS / "node_modules"
    if not link.exists() and not link.is_symlink():
        try:
            link.symlink_to(node_modules)
        except OSError:
            pass
    env["NODE_PATH"] = node_modules

try:
    proc = subprocess.run(
        cmd, cwd=WS, capture_output=True, text=True, timeout=CFG["timeout"], env=env
    )
except FileNotFoundError:
    fail(f"test runner {cmd[0]!r} not found on PATH")
except subprocess.TimeoutExpired:
    fail(f"test timed out after {CFG['timeout']}s")

if proc.returncode != 0:
    fail("test still fails:\\n" + (proc.stdout + proc.stderr)[-1500:])
print("PASS")
'''


def build_task(
    repo: Path,
    cand: Candidate,
    tasks_dir: Path,
    hide_tests: bool = False,
    prepared=None,
) -> Path:
    """Materialize ``cand`` as ``tasks_dir/<id>/`` and return the task directory."""
    if not cand.verified:
        raise MineError(f"refusing to build an unverified candidate {cand.short}")
    tid = _unique_id(tasks_dir, task_id(cand))
    root = tasks_dir / tid
    root.mkdir(parents=True, exist_ok=False)

    # Workspace starts as the full parent tree (buggy source, old tests).
    workspace = root / "workspace"
    _export_tree(repo, cand.parent, workspace)

    # Lock the commit's version of every changed test file.
    locked = root / "tests_locked"
    for rel in cand.test_files:
        content = file_at(repo, cand.sha, rel)
        if content is None:
            raise MineError(f"could not read test {rel} at {cand.short}")
        dst = locked / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        if not hide_tests:
            ws_file = workspace / rel
            ws_file.parent.mkdir(parents=True, exist_ok=True)
            ws_file.write_text(content, encoding="utf-8")

    # Reference solution: the commit's version of each source file (for the mock and
    # verify-tasks). A file the commit deleted is skipped; the hidden test still governs.
    solution = root / "solution"
    solution.mkdir(parents=True, exist_ok=True)
    wrote_solution = False
    for rel in cand.source_files:
        content = file_at(repo, cand.sha, rel)
        if content is None:
            continue
        dst = solution / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        wrote_solution = True
    if not wrote_solution:
        solution.rmdir()

    cmd = cand.runner.command(cand.test_files[0], cand.selectors)
    cmd_human = _human_cmd(cmd)
    check = {
        "runner": cand.runner.name,
        "language": cand.runner.language,
        "test_file": cand.test_files[0],
        "test_files": cand.test_files,
        "test_cmd": cmd,
        "hide_tests": hide_tests,
        "timeout": VERIFY_TIMEOUT,
        "setup": (prepared.install_cmd if prepared and prepared.install_cmd else cand.runner.setup),
        "commit": cand.sha,
        "parent": cand.parent,
    }
    if prepared and prepared.python:
        check["python"] = prepared.python
    if prepared and prepared.node_modules:
        check["node_modules"] = prepared.node_modules
    (root / "check.json").write_text(json.dumps(check, indent=2) + "\n", encoding="utf-8")
    (root / "verify.py").write_text(VERIFY_TEMPLATE, encoding="utf-8")
    _write_toml(root / "task.toml", cand, tid, _prompt(cand, hide_tests, cmd_human), hide_tests)
    return root


def _human_cmd(cmd: list[str]) -> str:
    return " ".join(cmd)


def _unique_id(tasks_dir: Path, base: str) -> str:
    tid = base
    n = 2
    while (tasks_dir / tid).exists():
        tid = f"{base}-{n}"
        n += 1
    return tid


def runner_setup_note(runner: Runner) -> str | None:
    """A one-line note about dependency setup, or None when none is needed."""
    if runner.setup is None:
        return None
    return " ".join(runner.setup)
