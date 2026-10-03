"""Hidden checks for minimal-fix: correct fix, and nothing outside paginate's body changed."""

import ast
import difflib
import sys
from pathlib import Path

ws = Path.cwd()
ORIGINAL = Path(__file__).resolve().parent / "workspace"
IGNORED = {"__pycache__", ".pytest_cache"}
sys.path.insert(0, str(ws))


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and not (set(p.relative_to(root).parts) & IGNORED)}


orig_files, now_files = files(ORIGINAL), files(ws)
if orig_files != now_files:
    fail(f"files added or removed: +{sorted(now_files - orig_files)} "
         f"-{sorted(orig_files - now_files)}")
for rel in sorted(orig_files - {"legacy.py"}):
    if (ws / rel).read_bytes() != (ORIGINAL / rel).read_bytes():
        fail(f"{rel} was modified")

from legacy import paginate, totalPages  # noqa: E402

items = list(range(1, 26))
checks = [((items, 1), list(range(1, 11))), ((items, 2), list(range(11, 21))),
          ((items, 3), list(range(21, 26))), ((items, 4), []), (([], 1), []),
          ((items, 1, 5), [1, 2, 3, 4, 5]), ((items, 5, 5), [21, 22, 23, 24, 25])]
for args, want in checks:
    got = paginate(*args)
    if got != want:
        fail(f"paginate{tuple(a if not isinstance(a, list) else '...' for a in args)} = {got}")
if totalPages(items) != 3:
    fail("totalPages changed")


def span(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno, node.end_lineno
    fail(f"function {name} not found")


old_src = (ORIGINAL / "legacy.py").read_text(encoding="utf-8")
new_src = (ws / "legacy.py").read_text(encoding="utf-8")
old_lines, new_lines = old_src.splitlines(), new_src.splitlines()
(o1, o2), (n1, n2) = span(old_src, "paginate"), span(new_src, "paginate")
if old_lines[:o1 - 1] != new_lines[:n1 - 1] or old_lines[o2:] != new_lines[n2:]:
    fail("legacy.py changed outside paginate")
body_diff = [ln for ln in difflib.unified_diff(old_lines[o1 - 1:o2], new_lines[n1 - 1:n2],
                                               lineterm="", n=0)
             if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
if len(body_diff) > 4:
    fail(f"paginate rewrite too large ({len(body_diff)} changed lines; a 1-line fix suffices)")
print("PASS")
