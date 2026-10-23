"""Find past bug-fix commits in a git repository that can be replayed as tasks.

A commit is *replayable* when it changed source files and added or changed a test, and that
test fails on the parent commit but passes on the commit itself. Both directions are checked
by actually running the test, so a candidate that survives is one a real agent could be asked
to reproduce.

The expensive part (checking out commits and running their tests) uses ``git worktree`` so
the user's own checkout is never touched. Everything writes only under a scratch directory
the caller owns.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .runners import Runner, detect_runner, is_source_file, is_test_file

# Narrow a run to the tests a commit actually touched, so an unrelated pre-existing failure in
# the same (often monolithic) test file does not make the task look unreplayable.
_DEF_RE = {
    "python": re.compile(r"\bdef\s+(test[A-Za-z0-9_]*)"),
    "go": re.compile(r"\bfunc\s+(Test[A-Za-z0-9_]*)"),
}
_JS_CALL = re.compile(r"\b(?:it|test)\(\s*[\"'`]([^\"'`]+)")


def changed_test_names(diff_text: str, language: str) -> tuple[str, ...]:
    """Names of the tests a test-file diff adds or changes, for a ``-k``/``-run`` selector.

    Python and Go attribute each changed line to its enclosing ``def``/``func``; JavaScript
    reads the string name of each ``test(...)``/``it(...)`` on a changed line. Empty means run
    the whole file.
    """
    names: set[str] = set()
    enclosing: str | None = None
    def_re = _DEF_RE.get(language)
    for line in diff_text.splitlines():
        if line.startswith(("@@", "+++", "---", "diff ")):
            enclosing = None
            continue
        tag, body = line[:1], line[1:]
        if tag in " +" and def_re:
            m = def_re.search(body)
            if m:
                enclosing = m.group(1)
        if tag in "+-":
            if enclosing:
                names.add(enclosing)
            if language == "javascript":
                for m in _JS_CALL.finditer(body):
                    names.add(m.group(1))
    return tuple(sorted(names))


# Commit subjects that advertise a bug fix, used only to rank, never to exclude.
FIX_WORDS = re.compile(
    r"\b(fix(e[ds])?|bug|regression|crash|broken|incorrect|wrong|error|fail(s|ed|ing)?|"
    r"issue|defect|patch|resolve[ds]?|repair)\b",
    re.IGNORECASE,
)
# Subjects that are almost never a single reproducible fix.
SKIP_WORDS = re.compile(
    r"\b(merge|revert|bump|release|version|changelog|readme|typo|lint|format|whitespace|"
    r"rename|refactor|cleanup|wip)\b",
    re.IGNORECASE,
)

MIN_FREE_BYTES = 3 * 1024**3  # stop before the disk drops under 3 GB


class MineError(RuntimeError):
    pass


@dataclass
class Candidate:
    sha: str
    parent: str
    subject: str
    body: str
    source_files: list[str]
    test_files: list[str]
    runner: Runner
    insertions: int
    deletions: int
    selectors: tuple[str, ...] = ()
    verified: bool = False
    test_seconds: float | None = None
    skip_reason: str | None = None
    parent_output: str = ""
    commit_output: str = ""

    @property
    def short(self) -> str:
        return self.sha[:10]

    @property
    def diff_size(self) -> int:
        return self.insertions + self.deletions

    @property
    def fix_score(self) -> int:
        return len(FIX_WORDS.findall(self.subject + " " + self.body))


def free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return MIN_FREE_BYTES


def _git(repo: Path, *args: str, check: bool = True, timeout: int = 120) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise MineError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists() or (
        path.is_dir()
        and subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--git-dir"],
            capture_output=True,
        ).returncode
        == 0
    )


def looks_like_url(spec: str) -> bool:
    return (
        "://" in spec
        or spec.startswith("git@")
        or bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", spec))
    )


def clone_url(spec: str) -> str:
    """Normalize a GitHub shorthand (``owner/repo``) to an https URL; pass URLs through."""
    if "://" in spec or spec.startswith("git@"):
        return spec
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", spec):
        return f"https://github.com/{spec}"
    return spec


def resolve_repo(spec: str, scratch: Path, commits: int) -> Path:
    """Return a local git checkout for ``spec``, cloning into ``scratch`` when needed.

    A local path is used in place (read-only; worktrees go under ``scratch``). A URL or
    ``owner/repo`` shorthand is cloned. The clone is deep enough to see ``commits`` history
    plus headroom, so parents of the oldest candidates are present.
    """
    local = Path(spec).expanduser()
    if not looks_like_url(spec) and local.exists():
        if not is_git_repo(local):
            raise MineError(f"{local} is not a git repository")
        return local.resolve()
    if free_bytes(scratch) < MIN_FREE_BYTES:
        raise MineError("less than 3 GB free; refusing to clone (clean up and retry)")
    url = clone_url(spec)
    dest = scratch / "clone"
    depth = str(max(commits * 3, 100))
    proc = subprocess.run(
        ["git", "clone", "--depth", depth, "--no-single-branch", url, str(dest)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise MineError(f"could not clone {url}: {proc.stderr.strip()[-400:]}")
    return dest


def recent_commits(repo: Path, limit: int) -> list[tuple[str, str, str, str]]:
    """``(sha, parent, subject, body)`` for the newest ``limit`` single-parent commits."""
    sep = "\x1e"
    rec = "\x1f"
    fmt = f"%H{sep}%P{sep}%s{sep}%b{rec}"
    out = _git(repo, "log", f"--max-count={limit * 2}", f"--pretty=format:{fmt}")
    rows = []
    for chunk in out.split(rec):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        sha, parents, subject, body = (chunk.split(sep) + ["", "", "", ""])[:4]
        parent_list = parents.split()
        if len(parent_list) != 1:  # skip merges and the initial commit
            continue
        rows.append((sha, parent_list[0], subject, body))
        if len(rows) >= limit:
            break
    return rows


def _numstat(repo: Path, parent: str, sha: str) -> dict[str, tuple[int, int]]:
    out = _git(repo, "diff", "--numstat", parent, sha)
    stats: dict[str, tuple[int, int]] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        ins = int(added) if added.isdigit() else 0
        dels = int(removed) if removed.isdigit() else 0
        stats[path] = (ins, dels)
    return stats


def find_candidates(repo: Path, limit: int) -> list[Candidate]:
    """Commits whose file changes look like 'a fix plus the test that proves it'."""
    out: list[Candidate] = []
    for sha, parent, subject, body in recent_commits(repo, limit):
        if SKIP_WORDS.search(subject):
            continue
        stats = _numstat(repo, parent, sha)
        if not stats:
            continue
        test_files = sorted(p for p in stats if is_test_file(p))
        source_files = sorted(p for p in stats if is_source_file(p))
        if not test_files or not source_files:
            continue
        runner, reason = detect_runner(repo, test_files[0])
        if runner is None:
            out.append(
                Candidate(
                    sha, parent, subject, body, source_files, test_files,
                    Runner("none", "?", None), 0, 0, skip_reason=reason or "no runner",
                )
            )
            continue
        ins = sum(stats[p][0] for p in (*source_files, *test_files))
        dels = sum(stats[p][1] for p in (*source_files, *test_files))
        file_diff = _git(repo, "diff", parent, sha, "--", test_files[0], check=False)
        selectors = changed_test_names(file_diff, runner.language)
        out.append(
            Candidate(
                sha, parent, subject, body, source_files, test_files, runner, ins, dels, selectors
            )
        )
    return out


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """Smaller diffs, clearer fix wording, and fewer files first."""
    return sorted(
        candidates,
        key=lambda c: (
            -min(c.fix_score, 3),
            len(c.source_files) + len(c.test_files),
            c.diff_size,
            c.subject.lower(),
        ),
    )


# ---- replay verification ---------------------------------------------------------------


@dataclass
class Worktree:
    path: Path
    repo: Path
    _added: bool = field(default=False, repr=False)

    def remove(self) -> None:
        if self._added:
            subprocess.run(
                ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self.path)],
                capture_output=True,
            )
        shutil.rmtree(self.path, ignore_errors=True)


def add_worktree(repo: Path, sha: str, dest: Path) -> Worktree:
    proc = subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", "--force", str(dest), sha],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise MineError(f"git worktree add {sha[:10]} failed: {proc.stderr.strip()[-300:]}")
    return Worktree(dest, repo, _added=True)


def _run_test(
    worktree: Path,
    runner: Runner,
    test_file: str,
    timeout: int,
    prepared=None,
    selectors: tuple[str, ...] = (),
) -> tuple[bool, str]:
    """Run ``test_file`` in ``worktree``. Returns ``(passed, output_tail)``.

    ``prepared`` is an optional :class:`~rerun_bench.envs.PreparedEnv`: for Python it supplies
    the interpreter that can import the repo's installed test dependencies, and for JavaScript
    it supplies a populated ``node_modules`` linked into the worktree.
    """
    from . import envs

    cmd = runner.command(test_file, selectors)
    interpreter = (prepared.python if prepared and prepared.python else None) or sys.executable
    if cmd and cmd[0] == "python":
        cmd = [interpreter, *cmd[1:]]
    if prepared and prepared.node_modules:
        envs.link_node_modules(prepared.node_modules, worktree)
    env = _test_env(worktree)
    if prepared and prepared.node_modules:
        env["NODE_PATH"] = prepared.node_modules
    try:
        proc = subprocess.run(
            cmd,
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return False, f"test runner {cmd[0]!r} not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    tail = (proc.stdout + proc.stderr)[-1500:]
    return proc.returncode == 0, tail


def _test_env(worktree: Path) -> dict[str, str]:
    import os

    env = dict(os.environ)
    paths = [str(worktree)]
    if (worktree / "src").is_dir():
        paths.append(str(worktree / "src"))
    existing = env.get("PYTHONPATH")
    if existing:
        paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def verify_candidate(
    repo: Path, cand: Candidate, scratch: Path, test_timeout: int = 120, prepared=None
) -> Candidate:
    """Run the candidate's test on the parent (must fail) and the commit (must pass).

    On success ``cand.verified`` is True. On failure ``cand.skip_reason`` says why, in plain
    language, so the caller can report what it skipped and why.
    """
    if cand.runner.name == "none":
        return cand
    if free_bytes(scratch) < MIN_FREE_BYTES:
        cand.skip_reason = "less than 3 GB free; skipped replay"
        return cand
    test_file = cand.test_files[0]
    wt_commit = wt_parent = None
    try:
        wt_commit = add_worktree(repo, cand.sha, scratch / f"wt-{cand.short}-commit")
        t0 = time.perf_counter()
        passed_c, out_c = _run_test(
            wt_commit.path, cand.runner, test_file, test_timeout, prepared, cand.selectors
        )
        cand.test_seconds = round(time.perf_counter() - t0, 2)
        cand.commit_output = out_c
        if not passed_c:
            cand.skip_reason = (
                "test did not pass on the fix commit (missing deps or not a unit test)"
            )
            return cand
        wt_parent = add_worktree(repo, cand.parent, scratch / f"wt-{cand.short}-parent")
        _overlay_tests(repo, cand, wt_parent.path)
        passed_p, out_p = _run_test(
            wt_parent.path, cand.runner, test_file, test_timeout, prepared, cand.selectors
        )
        cand.parent_output = out_p
        if passed_p:
            cand.skip_reason = "test already passed on the parent (does not isolate the fix)"
            return cand
        cand.verified = True
        return cand
    except MineError as exc:
        cand.skip_reason = str(exc)
        return cand
    finally:
        if wt_commit is not None:
            wt_commit.remove()
        if wt_parent is not None:
            wt_parent.remove()


def _overlay_tests(repo: Path, cand: Candidate, worktree: Path) -> None:
    """Copy the commit's version of each changed test file into the parent worktree."""
    for path in cand.test_files:
        content = _git(repo, "show", f"{cand.sha}:{path}", check=False)
        dest = worktree / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def file_at(repo: Path, sha: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{sha}:{path}"],
        capture_output=True,
        text=True,
    )
    return proc.stdout if proc.returncode == 0 else None


def tree_files(repo: Path, sha: str) -> list[str]:
    out = _git(repo, "ls-tree", "-r", "--name-only", sha)
    return [line for line in out.splitlines() if line]
