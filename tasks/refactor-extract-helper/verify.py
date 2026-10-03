"""Hidden checks for refactor-extract-helper: structure changed, behavior identical."""

import ast
import importlib.util
import sys
from pathlib import Path

ORIGINAL = Path(__file__).resolve().parent / "workspace" / "pricing.py"
CURRENT = Path.cwd() / "pricing.py"


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tree = ast.parse(CURRENT.read_text(encoding="utf-8"))
funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
if "clamp_percent" not in funcs:
    fail("no top-level function clamp_percent in pricing.py")
for name in ("member_price", "sale_price", "bulk_price"):
    fn = funcs.get(name)
    if fn is None:
        fail(f"{name} is missing")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "clamp_percent"]
    if not calls:
        fail(f"{name} does not call clamp_percent")
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare) and any(
                isinstance(c, ast.Name) and c.id == "MAX_DISCOUNT" for c in node.comparators):
            fail(f"{name} still contains its own clamping comparison")

old = load(ORIGINAL, "pricing_original")
new = load(CURRENT, "pricing_current")
percents = [-50, -1, -0.5, 0, 0.5, 10, 33.3, 89.99, 90, 90.01, 95, 100, 250]
prices = [0, 0.99, 1, 19.99, 100, 1234.56]
for p in prices:
    for pct in percents:
        if old.member_price(p, pct) != new.member_price(p, pct):
            fail(f"member_price({p}, {pct}) changed")
        for floor in (0, 1.0, 5):
            if old.sale_price(p, pct, floor) != new.sale_price(p, pct, floor):
                fail(f"sale_price({p}, {pct}, {floor}) changed")
        for q in (0, 1, 9, 10, 11, 100):
            if old.bulk_price(p, q, pct) != new.bulk_price(p, q, pct):
                fail(f"bulk_price({p}, {q}, {pct}) changed")
        if old.sale_price(p, pct) != new.sale_price(p, pct):
            fail(f"sale_price default floor changed for ({p}, {pct})")
if new.MAX_DISCOUNT != 90:
    fail("MAX_DISCOUNT changed")
print("PASS")
