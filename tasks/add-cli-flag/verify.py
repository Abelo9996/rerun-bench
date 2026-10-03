"""Hidden checks for add-cli-flag."""

import subprocess
import sys
import tempfile
from pathlib import Path

ws = Path.cwd()


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def run(*args, cwd):
    p = subprocess.run(
        [sys.executable, str(ws / "wc.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.returncode, p.stdout.replace("\r\n", "\n")


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "a.txt").write_text("one two three\nfour\n\nfive  six\n", encoding="utf-8")
    (d / "b.txt").write_text("  lonely   \n", encoding="utf-8")
    (d / "c.txt").write_text("", encoding="utf-8")
    expect = {
        ("a.txt",): "       4 a.txt\n",
        ("a.txt", "b.txt", "c.txt"): "       4 a.txt\n       1 b.txt\n       0 c.txt\n"
        "       5 total\n",
        ("--words", "a.txt"): "       6 a.txt\n",
        ("a.txt", "--words"): "       6 a.txt\n",
        ("--words", "a.txt", "b.txt", "c.txt"): "       6 a.txt\n       1 b.txt\n"
        "       0 c.txt\n       7 total\n",
    }
    for args, want in expect.items():
        code, out = run(*args, cwd=d)
        if code != 0 or out != want:
            fail(f"wc.py {' '.join(args)}: exit {code}, output {out!r}, want {want!r}")
    code, _ = run("--words", cwd=d)
    if code == 0:
        fail("wc.py --words with no files should exit non-zero")
print("PASS")
