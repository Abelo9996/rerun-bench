"""Hidden checks for write-tests: the agent's tests pass on the real code and kill mutants."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ws = Path.cwd()
TASK = Path(__file__).resolve().parent
ORIGINAL = TASK / "workspace"


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def run_tests(root):
    p = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return p.returncode, p.stdout + p.stderr


test_file = ws / "tests" / "test_duration.py"
if not test_file.is_file():
    fail("tests/test_duration.py does not exist")
if (ws / "duration.py").read_bytes() != (ORIGINAL / "duration.py").read_bytes():
    fail("duration.py was modified")
code, out = run_tests(ws)
if code != 0:
    fail("tests fail against the real implementation:\n" + out[-1500:])
if "Ran 0 tests" in out:
    fail("no tests were collected")

survivors = []
for mutant in sorted((TASK / "mutants").glob("*.py")):
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / "ws"
        shutil.copytree(ws, copy, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(mutant, copy / "duration.py")
        code, _ = run_tests(copy)
        if code == 0:
            survivors.append(mutant.stem)
if survivors:
    fail(f"tests did not catch these injected bugs: {', '.join(survivors)}")
print("PASS")
