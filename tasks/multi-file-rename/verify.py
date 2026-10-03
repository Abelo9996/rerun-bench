"""Hidden checks for multi-file-rename."""

import importlib
import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

ws = Path.cwd()
sys.path.insert(0, str(ws))


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


for py in sorted((ws / "inventory").rglob("*.py")):
    if "calc_ttl" in py.read_text(encoding="utf-8"):
        fail(f"{py.relative_to(ws).as_posix()} still mentions calc_ttl")
inv = importlib.import_module("inventory")
pricing = importlib.import_module("inventory.pricing")
cli = importlib.import_module("inventory.cli")
if not callable(getattr(inv, "compute_total", None)):
    fail("inventory.compute_total is not exported")
if "compute_total" not in getattr(inv, "__all__", []):
    fail("compute_total missing from inventory.__all__")
for mod in (inv, pricing):
    if hasattr(mod, "calc_ttl"):
        fail(f"{mod.__name__}.calc_ttl still exists")
if inv.compute_total([(3, 2.5), (1, 4.0)]) != 11.5:
    fail("compute_total returns the wrong value")
buf = io.StringIO()
with redirect_stdout(buf):
    cli.main(["3x2.50", "1x4"])
if buf.getvalue() != "2 lines, total 11.50\ncheck: 11.50\n":
    fail(f"cli output changed: {buf.getvalue()!r}")
proc = subprocess.run(
    [sys.executable, "-m", "inventory.cli", "2x1.25", "4x0.5"],
    cwd=ws,
    capture_output=True,
    text=True,
    timeout=60,
)
if (
    proc.returncode != 0
    or proc.stdout.replace("\r\n", "\n") != "2 lines, total 4.50\ncheck: 4.50\n"
):
    fail(f"python -m inventory.cli failed: {proc.stdout!r} {proc.stderr[-500:]!r}")
print("PASS")
