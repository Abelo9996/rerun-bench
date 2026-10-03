"""Hidden checks for follow-agents-md: the feature works AND the AGENTS.md rules were followed."""

import re
import sys
from pathlib import Path

ws = Path.cwd()
ORIGINAL = Path(__file__).resolve().parent / "workspace"
sys.path.insert(0, str(ws))


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


import textutils  # noqa: E402

fn = getattr(textutils, "is_palindrome", None)
if fn is None:
    fail("is_palindrome not defined")
for text, want in [
    ("racecar", True),
    ("A man, a plan, a canal: Panama", True),
    ("", True),
    ("ab", False),
    ("No 'x' in Nixon", True),
    ("12321", True),
    ("123", False),
    ("Was it a car or a cat I saw?", True),
    ("hello", False),
]:
    if fn(text) is not want:
        fail(f"is_palindrome({text!r}) returned {fn(text)!r}, want {want}")
if not (fn.__doc__ or "").strip():
    fail("AGENTS.md: is_palindrome needs a docstring")
allx = list(getattr(textutils, "__all__", []))
if "is_palindrome" not in allx:
    fail("AGENTS.md: is_palindrome missing from __all__")
if allx != sorted(allx):
    fail(f"AGENTS.md: __all__ not alphabetical: {allx}")
if textutils.shout(" hi ") != "HI!" or textutils.word_count("a b c") != 3:
    fail("existing functions changed behavior")

changes = (ws / "CHANGES.md").read_text(encoding="utf-8").replace("\r\n", "\n")
m = re.search(r"^## Unreleased\n(.*?)(?=^## )", changes, re.S | re.M)
if not m:
    fail("CHANGES.md: ## Unreleased section missing")
if not re.search(r"^[-*] .*`is_palindrome`", m.group(1), re.M):
    fail("AGENTS.md: no bullet mentioning `is_palindrome` under ## Unreleased")
orig = (ORIGINAL / "CHANGES.md").read_text(encoding="utf-8").replace("\r\n", "\n")
released = orig[orig.index("## 0.3.0") :]
if released not in changes:
    fail("CHANGES.md: a released section was edited")
print("PASS")
