"""The ``mine`` and ``from-test`` commands: build tasks from a repo's own history.

These wire the mining (``mining``), task building (``taskgen``) and the existing run and
report pipeline into one call, so ``rerun-bench mine .`` goes from a git history to the
flip-first headline without the user authoring a task by hand.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import mining, taskgen
from .mining import Candidate, MineError


@dataclass
class MineOutcome:
    repo: Path
    tasks_dir: Path
    built: list[tuple[str, Candidate]] = field(default_factory=list)
    verified_skipped: list[Candidate] = field(default_factory=list)
    no_runner: list[Candidate] = field(default_factory=list)
    scratch: Path | None = None
    cloned: bool = False

    def cleanup(self) -> None:
        if self.scratch is not None:
            shutil.rmtree(self.scratch, ignore_errors=True)


def _echo(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def mine_tasks(
    spec: str,
    tasks_dir: Path,
    *,
    want: int,
    history: int,
    hide_tests: bool,
    test_timeout: int,
    keep_scratch: bool = False,
) -> MineOutcome:
    """Clone or open ``spec``, find replayable fixes, and build up to ``want`` tasks.

    Writes progress to stderr so the stdout stays the report. Raises ``MineError`` on a
    problem that stops the whole command (bad repo, no candidates at all).
    """
    scratch = Path(tempfile.mkdtemp(prefix="rerun-bench-mine-"))
    out = MineOutcome(repo=Path(spec), tasks_dir=tasks_dir, scratch=scratch)
    try:
        repo = mining.resolve_repo(spec, scratch, history)
        out.repo = repo
        out.cloned = repo != Path(spec).expanduser().resolve() if Path(spec).exists() else True
        _echo(f"scanning the last {history} commits of {repo} ...")
        candidates = mining.find_candidates(repo, history)
        with_runner = [c for c in candidates if c.runner.name != "none"]
        out.no_runner = [c for c in candidates if c.runner.name == "none"]
        ranked = mining.rank(with_runner)
        _echo(
            f"found {len(ranked)} commit(s) that changed source and a test; "
            f"checking which replay (want {want}) ..."
        )
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for cand in ranked:
            if len(out.built) >= want:
                break
            cand = mining.verify_candidate(repo, cand, scratch, test_timeout=test_timeout)
            if not cand.verified:
                out.verified_skipped.append(cand)
                _echo(f"  skip  {cand.short}  {cand.subject[:60]!r}: {cand.skip_reason}")
                continue
            try:
                root = taskgen.build_task(repo, cand, tasks_dir, hide_tests=hide_tests)
            except MineError as exc:
                cand.skip_reason = f"could not build task: {exc}"
                out.verified_skipped.append(cand)
                _echo(f"  skip  {cand.short}: {cand.skip_reason}")
                continue
            out.built.append((root.name, cand))
            _echo(f"  built {root.name}  ({cand.test_seconds}s test, {cand.diff_size} diff lines)")
        if not out.built:
            raise MineError(
                "no replayable fix commits found. A replayable commit changes source files "
                "and adds or changes a test that fails before the change and passes after. "
                "Try --history to scan further back, or point at a repo with unit tests."
            )
        return out
    except Exception:
        if not keep_scratch:
            out.cleanup()
            out.scratch = None
        raise


def from_test_candidate(
    repo: Path, test_id: str, commit: str | None, scratch: Path, test_timeout: int
) -> Candidate:
    """Build and verify a single candidate for ``test_id`` (a repo-relative test file path)."""
    test_file = test_id.split("::", 1)[0]
    if commit is None:
        commit = _last_commit_touching(repo, test_file)
        if commit is None:
            raise MineError(
                f"could not find a commit that changed {test_file}; pass --commit <sha>"
            )
    parent = _parent_of(repo, commit)
    if parent is None:
        raise MineError(f"{commit[:10]} has no single parent (a merge or the first commit)")
    stats = mining._numstat(repo, parent, commit)
    if test_file not in stats and mining.file_at(repo, commit, test_file) is None:
        raise MineError(f"{test_file} does not exist at {commit[:10]}")
    source_files = sorted(p for p in stats if mining.is_source_file(p))
    test_files = sorted({p for p in stats if mining.is_test_file(p)} | {test_file})
    runner, reason = mining.detect_runner(repo, test_file)
    if runner is None:
        raise MineError(reason or f"no runner for {test_file}")
    subject, body = _commit_message(repo, commit)
    ins = sum(stats.get(p, (0, 0))[0] for p in (*source_files, *test_files))
    dels = sum(stats.get(p, (0, 0))[1] for p in (*source_files, *test_files))
    cand = Candidate(
        commit, parent, subject, body, source_files or test_files, test_files, runner, ins, dels
    )
    return mining.verify_candidate(repo, cand, scratch, test_timeout=test_timeout)


def _last_commit_touching(repo: Path, path: str) -> str | None:
    out = mining._git(repo, "log", "-1", "--format=%H", "--", path, check=False).strip()
    return out or None


def _parent_of(repo: Path, sha: str) -> str | None:
    out = mining._git(repo, "rev-list", "--parents", "-n", "1", sha, check=False).split()
    return out[1] if len(out) == 2 else None


def _commit_message(repo: Path, sha: str) -> tuple[str, str]:
    subject = mining._git(repo, "log", "-1", "--format=%s", sha).strip()
    body = mining._git(repo, "log", "-1", "--format=%b", sha).strip()
    return subject, body


def summarize(out: MineOutcome) -> list[str]:
    """Plain lines describing what was mined and what was skipped and why (for stderr)."""
    lines = [
        "",
        f"Mined {len(out.built)} task(s) from {out.repo}:",
    ]
    for tid, cand in out.built:
        lines.append(f"  {tid}")
        lines.append(f"      {cand.subject[:72]}")
    if out.verified_skipped:
        lines.append("")
        lines.append(f"Skipped {len(out.verified_skipped)} commit(s) that did not replay:")
        for cand in out.verified_skipped[:10]:
            lines.append(f"  {cand.short}  {cand.subject[:50]!r}: {cand.skip_reason}")
        if len(out.verified_skipped) > 10:
            lines.append(f"  ... and {len(out.verified_skipped) - 10} more")
    if out.no_runner:
        lines.append("")
        lines.append(
            f"{len(out.no_runner)} commit(s) changed a test but no runner was detected "
            "(unsupported language or layout)."
        )
    return lines
