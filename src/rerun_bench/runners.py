"""Detect a repository's test runner and build the command that runs one test.

A runner is detected from files in the repository root (``pyproject.toml``, ``package.json``,
``go.mod``, ``Cargo.toml``) and from the path of the test file itself. The command is kept as
a list with a leading ``"python"`` token where the interpreter belongs; the generated
``verify.py`` swaps that token for its own ``sys.executable`` so the hidden check and the
mining step use the same Python.

Everything here is a pure function of paths and file contents, so it is unit-testable without
a repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Runner:
    """A detected test runner and how to invoke it for a single test file."""

    name: str  # pytest | unittest | node-test | npm | go | cargo
    language: str  # python | javascript | go | rust
    setup: list[str] | None  # best-effort dependency install, or None when none is needed

    def command(self, test_file: str, selectors: tuple[str, ...] = ()) -> list[str]:
        """Command that runs just ``test_file`` (a repo-relative posix path).

        ``selectors`` names the specific tests the fix commit touched. When given, the command
        runs only those, so an unrelated pre-existing failure elsewhere in a monolithic test
        file does not make the task look unreplayable.
        """
        if self.name == "pytest":
            cmd = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", test_file]
            if selectors:
                cmd += ["-k", " or ".join(selectors)]
            return cmd
        if self.name == "unittest":
            module = test_file[:-3].replace("/", ".")
            return ["python", "-m", "unittest", "-q", module]
        if self.name == "node-test":
            cmd = ["node", "--test"]
            for name in selectors:
                cmd += ["--test-name-pattern", name]
            return [*cmd, test_file]
        if self.name == "npm":
            return ["npm", "test", "--", test_file]
        if self.name == "go":
            pkg = "./" + str(PurePosixPath(test_file).parent)
            cmd = ["go", "test", pkg]
            if selectors:
                cmd += ["-run", "|".join(selectors)]
            return cmd
        if self.name == "cargo":
            return ["cargo", "test", *selectors]
        raise ValueError(f"unknown runner {self.name!r}")


# File-name patterns that mark a path as a test, per language. Ordered most specific first.
TEST_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "python": (
        re.compile(r"(^|/)test_[^/]+\.py$"),
        re.compile(r"(^|/)[^/]+_test\.py$"),
        re.compile(r"(^|/)conftest\.py$"),
        re.compile(r"(^|/)tests?/.+\.py$"),
    ),
    "javascript": (
        re.compile(r"(^|/)[^/]+\.(test|spec)\.(js|mjs|cjs|jsx|ts|tsx)$"),
        re.compile(r"(^|/)__tests__/.+\.(js|mjs|cjs|jsx|ts|tsx)$"),
        re.compile(r"(^|/)tests?/.+\.(js|mjs|cjs|jsx|ts|tsx)$"),
        re.compile(r"(^|/)test\.(js|mjs|cjs|jsx|ts|tsx)$"),
    ),
    "go": (re.compile(r"(^|/)[^/]+_test\.go$"),),
    "rust": (re.compile(r"(^|/)tests/.+\.rs$"),),
}

# A changed file is treated as source (not test, not noise) when it is none of these.
NON_SOURCE_SUFFIXES = {
    ".md",
    ".txt",
    ".rst",
    ".lock",
    ".cfg",
    ".ini",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".gitignore",
    ".png",
    ".svg",
    ".jpg",
    ".gif",
}


def test_language(path: str) -> str | None:
    """Language of a test file by its path, or ``None`` if the path is not a test file."""
    for lang, patterns in TEST_PATTERNS.items():
        if any(p.search(path) for p in patterns):
            return lang
    return None


def is_test_file(path: str) -> bool:
    return test_language(path) is not None


def is_source_file(path: str) -> bool:
    """Whether a changed path is plausibly a source file the fix would have touched."""
    if is_test_file(path):
        return False
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in NON_SOURCE_SUFFIXES or not suffix:
        return False
    return suffix in {
        ".py",
        ".js",
        ".mjs",
        ".cjs",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
    }


def _read(root: Path, name: str) -> str:
    try:
        return (root / name).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def detect_runner(repo_root: Path, test_file: str) -> tuple[Runner | None, str | None]:
    """Detect the runner for ``test_file`` in ``repo_root``.

    Returns ``(runner, None)`` on success or ``(None, reason)`` with a plain refusal when the
    environment cannot be worked out. The test file's language is decided first; the project
    metadata then chooses between runners of that language.
    """
    lang = test_language(test_file)
    if lang is None:
        return None, f"{test_file} does not look like a test file"
    if lang == "python":
        return _detect_python(repo_root, test_file)
    if lang == "javascript":
        return _detect_javascript(repo_root, test_file)
    if lang == "go":
        if not (repo_root / "go.mod").is_file():
            return None, "Go test file but no go.mod at the repository root"
        return Runner("go", "go", setup=None), None
    if lang == "rust":
        if not (repo_root / "Cargo.toml").is_file():
            return None, "Rust test file but no Cargo.toml at the repository root"
        return Runner("cargo", "rust", setup=["cargo", "build", "--tests"]), None
    return None, f"no runner known for {lang}"


def _detect_python(repo_root: Path, test_file: str) -> tuple[Runner | None, str | None]:
    """Python test files always run under pytest.

    pytest discovers both plain ``test_*`` functions and ``unittest.TestCase`` classes, so it
    is the one runner that works for either style; plain ``python -m unittest`` silently
    collects nothing from function-style tests. The install command is recorded for
    information only: a flat-layout module at the repo root needs nothing, while a packaged
    project needs an editable install for its imports to resolve.
    """
    setup: list[str] = ["python", "-m", "pip", "install", "pytest"]
    if (repo_root / "pyproject.toml").is_file() or (repo_root / "setup.py").is_file():
        setup = ["python", "-m", "pip", "install", "pytest", "-e", "."]
    return Runner("pytest", "python", setup=setup), None


def _detect_javascript(repo_root: Path, test_file: str) -> tuple[Runner | None, str | None]:
    import json

    pkg_path = repo_root / "package.json"
    if not pkg_path.is_file():
        # A lone *.test.js with no package.json: node's built-in runner can still run it.
        return Runner("node-test", "javascript", setup=None), None
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pkg = {}
    scripts = pkg.get("scripts") or {}
    setup = ["npm", "ci"] if (repo_root / "package-lock.json").is_file() else ["npm", "install"]
    test_script = scripts.get("test", "")
    # A test script that just errors out ("no test specified") is not usable.
    if test_script and "no test specified" not in test_script:
        if "--test" in test_script or test_script.strip() in ("node --test", "node:test"):
            return Runner("node-test", "javascript", setup=setup), None
        return Runner("npm", "javascript", setup=setup), None
    return Runner("node-test", "javascript", setup=setup), None
