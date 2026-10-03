"""Hidden checks for fix-failing-test. Run with cwd = the agent's workspace."""

import subprocess
import sys
from pathlib import Path

ORIGINAL = Path(__file__).resolve().parent / "workspace"
ws = Path.cwd()
sys.path.insert(0, str(ws))


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


if (ws / "test_stats.py").read_bytes() != (ORIGINAL / "test_stats.py").read_bytes():
    fail("test_stats.py was modified")

proc = subprocess.run(
    [sys.executable, "-m", "unittest", "-q"], cwd=ws, capture_output=True, text=True, timeout=60
)
if proc.returncode != 0:
    fail("visible tests fail:\n" + proc.stderr[-1500:])

from stats import mean, median  # noqa: E402

cases = [
    ([5], 5),
    ([3, 1, 2], 2),
    ([4, 1, 3, 2], 2.5),
    ([1.0, 2.0], 1.5),
    ([10, -10], 0),
    ([7, 7, 7, 7], 7),
    ([1, 2, 3, 4, 5, 6], 3.5),
]
for xs, want in cases:
    got = median(list(xs))
    if got != want:
        fail(f"median({xs}) = {got!r}, want {want!r}")
data = [3, 1, 2, 4]
median(data)
if data != [3, 1, 2, 4]:
    fail("median mutated its input")
for fn in (mean, median):
    try:
        fn([])
    except ValueError:
        pass
    else:
        fail(f"{fn.__name__}([]) should raise ValueError")
if mean([1, 2, 3, 4]) != 2.5:
    fail("mean changed behavior")
print("PASS")
