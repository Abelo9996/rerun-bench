"""Fresh per-run workspace copies and diff capture (no git dependency)."""

from __future__ import annotations

import difflib
import re
import shutil
import tempfile
from pathlib import Path

IGNORE_DIRS = {"__pycache__", ".pytest_cache", ".git", ".ruff_cache", ".mypy_cache", "node_modules"}
IGNORE_SUFFIXES = {".pyc", ".pyo"}


def _ignore(_dir: str, names: list[str]) -> list[str]:
    return [n for n in names if n in IGNORE_DIRS or Path(n).suffix in IGNORE_SUFFIXES]


def fresh_copy(src: Path, prefix: str = "rerun-bench-") -> Path:
    """Copy ``src`` into a brand-new temp directory and return the copy's path."""
    parent = Path(tempfile.mkdtemp(prefix=prefix))
    dest = parent / "workspace"
    shutil.copytree(src, dest, ignore=_ignore)
    return dest


def overlay(src: Path, dest: Path) -> None:
    """Copy every file under ``src`` onto ``dest``, overwriting."""
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=_ignore)


def cleanup(workspace: Path) -> None:
    shutil.rmtree(workspace.parent, ignore_errors=True)


def _files(root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in IGNORE_DIRS for part in rel.parts) or p.suffix in IGNORE_SUFFIXES:
            continue
        if p.is_file():
            out[rel.as_posix()] = p
    return out


def _read_lines(p: Path | None) -> list[str] | None:
    if p is None:
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    return text.replace("\r\n", "\n").splitlines(keepends=True)


def unified_diff(before: Path, after: Path) -> str:
    """Unified diff of all text files between two directory trees (paths are posix, sorted)."""
    a_files, b_files = _files(before), _files(after)
    chunks: list[str] = []
    for rel in sorted(set(a_files) | set(b_files)):
        a_lines = _read_lines(a_files.get(rel))
        b_lines = _read_lines(b_files.get(rel))
        if a_lines is None or b_lines is None:
            if (
                a_files.get(rel) is None
                or b_files.get(rel) is None
                or (a_files[rel].read_bytes() != b_files[rel].read_bytes())
            ):
                chunks.append(f"Binary files a/{rel} and b/{rel} differ\n")
            continue
        if a_lines == b_lines:
            continue
        a_name = f"a/{rel}" if rel in a_files else "/dev/null"
        b_name = f"b/{rel}" if rel in b_files else "/dev/null"
        for line in difflib.unified_diff(a_lines, b_lines, a_name, b_name, n=3):
            chunks.append(
                line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
            )
    return "".join(chunks)


_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def changed_lines(diff: str) -> set[str]:
    """The set of ``<file>:<+|-><line>`` entries in a unified diff, used for approach similarity.

    Trailing whitespace is stripped so whitespace noise does not count as a different approach.
    Context lines are ignored. Hunk headers are parsed with their line counts so content lines
    that happen to start with ``---``/``+++`` are not mistaken for file headers.
    """
    out: set[str] = set()
    current = "?"
    old_left = new_left = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            tag, body = line[:1], line[1:].rstrip()
            if tag == "-":
                old_left -= 1
                out.add(f"{current}:-{body}")
            elif tag == "+":
                new_left -= 1
                out.add(f"{current}:+{body}")
            elif tag == " ":
                old_left -= 1
                new_left -= 1
            continue
        if line.startswith("--- "):
            name = line[4:]
            if name != "/dev/null":
                current = name.removeprefix("a/")
        elif line.startswith("+++ "):
            name = line[4:]
            if name != "/dev/null":
                current = name.removeprefix("b/")
        else:
            m = _HUNK.match(line)
            if m:
                old_left = int(m.group(1)) if m.group(1) is not None else 1
                new_left = int(m.group(2)) if m.group(2) is not None else 1
    return out
