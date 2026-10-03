"""Hidden checks for implement-slugify."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


try:
    from textkit.slug import slugify
except Exception as exc:  # noqa: BLE001
    fail(f"import error: {exc!r}")

cases = [
    (("Hello, World!",), "hello-world"),
    (("  --Leading and trailing--  ",), "leading-and-trailing"),
    (("Café crème brûlée",), "cafe-creme-brulee"),
    (("multiple   spaces\tand\nnewlines",), "multiple-spaces-and-newlines"),
    (("C++ & Python 3.12",), "c-python-3-12"),
    (("日本語",), "n-a"),
    (("",), "n-a"),
    (("!!!",), "n-a"),
    (("already-a-slug",), "already-a-slug"),
    (("abc def ghi", 7), "abc-def"),
    (("abc def ghi", 4), "abc"),
    (("abcdef", 3), "abc"),
    (("UPPER_snake_Case",), "upper-snake-case"),
    (("x" * 60,), "x" * 50),
    (("ＡＢＣ",), "abc"),
]
try:
    for args, want in cases:
        got = slugify(*args)
        if got != want:
            fail(f"slugify{args!r} = {got!r}, want {want!r}")
except NotImplementedError:
    fail("slugify is not implemented")
for bad in (0, -1):
    try:
        slugify("abc", bad)
    except ValueError:
        continue
    fail(f"slugify('abc', {bad}) should raise ValueError")
print("PASS")
