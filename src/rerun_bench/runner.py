"""Execute a benchmark: every selected task, N independent runs, one fresh workspace each."""

from __future__ import annotations

import json
import platform
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from . import workspace as ws
from .adapters import Adapter, AgentResult, Usage
from .adapters.mock import MockAdapter
from .metrics import is_agent_error
from .tasks import Task, verify

SCHEMA_VERSION = 1


@dataclass
class RunPlan:
    tasks: list[Task]
    runs: int
    seed: int = 0
    jobs: int = 1
    keep_workspaces: bool = False
    # Stop after this many runs in a row end in an agent error (0 = never stop). A login,
    # quota or rate-limit problem otherwise turns into a long list of failed runs that look
    # like the agent's fault.
    max_consecutive_errors: int = 3


class RunStopped(Exception):
    """The run ended early. ``out_dir`` holds every run recorded so far."""

    def __init__(self, out_dir: Path, reason: str, done: int, planned: int, errors=()):
        super().__init__(reason)
        self.out_dir = out_dir
        self.reason = reason
        self.done = done
        self.planned = planned
        self.errors = list(errors)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "default"


def make_run_id(agent: str, model: str | None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{_slug(agent)}_{_slug(model or 'default')}_{now.strftime('%Y%m%dT%H%M%SZ')}"


def execute_one(
    adapter: Adapter,
    task: Task,
    run_index: int,
    seed: int,
    out_dir: Path,
    keep_workspace: bool = False,
) -> dict:
    work = ws.fresh_copy(task.workspace)
    pristine = ws.fresh_copy(task.workspace)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        if isinstance(adapter, MockAdapter):
            adapter.solution_dir = task.solution
        try:
            result = adapter.run(
                task.prompt,
                work,
                timeout=task.timeout,
                seed=seed,
                run_key=f"{task.id}/{run_index}",
            )
        except Exception as exc:  # an adapter bug must not lose the other runs
            result = AgentResult(None, 0.0, False, Usage(), error=f"adapter error: {exc!r}")
        if result.error is None and not result.timed_out:
            if result.exit_code not in (0, None) or result.usage.is_error is True:
                why = adapter.describe_error(result.stdout_tail, result.stderr_tail)
                result.error = (
                    f"exit code {result.exit_code}: {why}"
                    if result.exit_code not in (0, None)
                    else f"agent reported an error: {why}"
                )
        vres = verify(task, work)
        diff = ws.unified_diff(pristine, work)
    finally:
        ws.cleanup(pristine)
        if not keep_workspace:
            ws.cleanup(work)
    diff_rel = Path("diffs") / task.id / f"run{run_index:03d}.diff"
    (out_dir / diff_rel).parent.mkdir(parents=True, exist_ok=True)
    (out_dir / diff_rel).write_text(diff, encoding="utf-8")
    added = sum(1 for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    files = sorted(
        {ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/")}
        | {ln[6:] for ln in diff.splitlines() if ln.startswith("--- a/")}
    )
    u = result.usage
    return {
        "task_id": task.id,
        "run_index": run_index,
        "started_at": started,
        "passed": vres.passed,
        "verify_exit_code": vres.exit_code,
        "verify_timed_out": vres.timed_out,
        "verify_output_tail": _scrub_paths(vres.output, work, task.root)[-1000:],
        "agent_exit_code": result.exit_code,
        "agent_timed_out": result.timed_out,
        "agent_error": _scrub_paths(result.error, work, task.root) if result.error else None,
        "agent_stdout_tail": _scrub_paths(result.stdout_tail, work, task.root)[-2000:],
        "agent_stderr_tail": _scrub_paths(result.stderr_tail, work, task.root)[-1000:],
        "wall_time_s": round(result.wall_time_s, 3),
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_tokens": u.cache_read_tokens,
        "cache_write_tokens": u.cache_write_tokens,
        "total_tokens": u.total_tokens,
        "cost_usd": u.cost_usd,
        "model": u.model or adapter.model,
        "num_turns": u.num_turns,
        "is_error": u.is_error,
        "diff_path": diff_rel.as_posix(),
        "lines_added": added,
        "lines_removed": removed,
        "files_changed": files,
        "workspace": str(work) if keep_workspace else None,
        "extra": result.extra,
    }


def _scrub_paths(text: str, workspace: Path, task_root: Path) -> str:
    """Replace machine-specific absolute paths so result files can be shared as they are."""
    subs = []
    for path, label in ((workspace, "<workspace>"), (task_root, "<task>")):
        for variant in {str(path), str(path.resolve())}:
            subs.append((variant, label))
    home = Path.home()
    subs += [(str(home), "~"), (str(home.resolve()), "~")]
    for variant, label in sorted(subs, key=lambda s: -len(s[0])):
        if len(variant) > 1:
            text = text.replace(variant, label)
    return text


def run_benchmark(
    adapter: Adapter,
    plan: RunPlan,
    out_root: Path,
    run_id: str | None = None,
    progress: Callable[[dict], None] | None = None,
    resume: bool = False,
) -> Path:
    """Run the plan and write ``<out_root>/<run_id>/{meta.json,runs.jsonl,diffs/}``.

    Runs are interleaved (run 0 of every task, then run 1, ...) so that drift over the
    session, such as rate limiting or a provider-side change, spreads across tasks instead
    of landing on whichever task happened to run last.

    With ``resume=True`` and an existing ``run_id`` directory, runs already recorded in
    ``runs.jsonl`` are skipped and only the missing ``(task, run_index)`` pairs execute. The
    agent and model must match the original ``meta.json``.
    """
    explicit = run_id is not None
    run_id = run_id or make_run_id(adapter.name, adapter.model)
    out_dir = out_root / run_id
    if resume and explicit and (out_dir / "meta.json").is_file():
        return _resume(adapter, plan, out_dir, progress)
    if out_dir.exists() and not explicit:
        n = 2
        while (out_root / f"{run_id}-{n}").exists():
            n += 1
        run_id = f"{run_id}-{n}"
        out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "rerun_bench_version": __version__,
        "agent": adapter.name,
        "model": adapter.model,
        "agent_options": adapter.options,
        "cli_version": adapter.version(),
        "runs_per_task": plan.runs,
        "seed": plan.seed,
        "tasks": [t.id for t in plan.tasks],
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": f"{platform.system()} {platform.machine()} py{platform.python_version()}",
    }
    _write_meta(out_dir, meta)
    jobs = [(t, i) for i in range(plan.runs) for t in plan.tasks]
    t0 = time.perf_counter()
    try:
        elapsed = _execute(adapter, plan, jobs, out_dir, progress)
    except RunStopped as exc:
        meta["stopped"] = exc.reason
        meta["elapsed_s"] = round(time.perf_counter() - t0, 3)
        _write_meta(out_dir, meta)
        raise
    meta.pop("stopped", None)
    meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    meta["elapsed_s"] = round(elapsed, 3)
    _write_meta(out_dir, meta)
    return out_dir


def _resume(
    adapter: Adapter, plan: RunPlan, out_dir: Path, progress: Callable[[dict], None] | None
) -> Path:
    meta = check_resumable(out_dir, adapter)
    runs_path = out_dir / "runs.jsonl"
    done_rows = _read_runs(runs_path) if runs_path.is_file() else []
    # Rewrite the file so a line truncated by an interrupted write cannot corrupt the next one.
    runs_path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in done_rows), encoding="utf-8"
    )
    done = {(r["task_id"], r["run_index"]) for r in done_rows}
    jobs = [(t, i) for i in range(plan.runs) for t in plan.tasks if (t.id, i) not in done]
    meta["runs_per_task"] = max(int(meta.get("runs_per_task") or 0), plan.runs)
    meta["tasks"] = list(dict.fromkeys([*meta.get("tasks", []), *(t.id for t in plan.tasks)]))
    cli_version = adapter.version()
    if cli_version != meta.get("cli_version"):
        meta.setdefault("cli_versions_seen", [meta.get("cli_version")])
        if cli_version not in meta["cli_versions_seen"]:
            meta["cli_versions_seen"].append(cli_version)
    meta.setdefault("resumed_at", []).append(datetime.now(UTC).isoformat(timespec="seconds"))
    _write_meta(out_dir, meta)
    previous = float(meta.get("elapsed_s") or 0.0)
    t0 = time.perf_counter()
    try:
        elapsed = _execute(adapter, plan, jobs, out_dir, progress)
    except RunStopped as exc:
        meta["stopped"] = exc.reason
        meta["elapsed_s"] = round(previous + time.perf_counter() - t0, 3)
        _write_meta(out_dir, meta)
        raise
    meta.pop("stopped", None)
    meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    meta["elapsed_s"] = round(previous + elapsed, 3)
    _write_meta(out_dir, meta)
    return out_dir


def check_resumable(out_dir: Path, adapter: Adapter) -> dict:
    """Return ``out_dir``'s meta, or raise ``ValueError`` if ``adapter`` does not match it."""
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    if meta.get("agent") != adapter.name or meta.get("model") != adapter.model:
        raise ValueError(
            f"cannot resume {out_dir}: it was recorded with agent={meta.get('agent')!r} "
            f"model={meta.get('model')!r}, not agent={adapter.name!r} model={adapter.model!r}"
        )
    return meta


def _write_meta(out_dir: Path, meta: dict) -> None:
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _execute(
    adapter: Adapter,
    plan: RunPlan,
    jobs: list[tuple[Task, int]],
    out_dir: Path,
    progress: Callable[[dict], None] | None,
) -> float:
    """Run ``jobs`` and append one line per run to ``runs.jsonl``. Returns elapsed seconds.

    Raises ``RunStopped`` on Ctrl-C, or when ``plan.max_consecutive_errors`` runs in a row
    end in an agent error. In the second case those runs are moved from ``runs.jsonl`` to
    ``errors.jsonl``, so ``--resume`` runs them again once the setup is fixed.
    """
    lock = threading.Lock()
    runs_path = out_dir / "runs.jsonl"
    t0 = time.perf_counter()
    stop = threading.Event()
    interrupted = threading.Event()
    streak: list[dict] = []
    done = 0

    def _do(job: tuple[Task, int]) -> None:
        nonlocal done
        if stop.is_set():
            return
        task, idx = job
        # Each worker gets its own adapter instance state for the mock's solution_dir.
        local = adapter if plan.jobs == 1 else type(adapter)(adapter.model, adapter.options)
        rec = execute_one(local, task, idx, plan.seed, out_dir, plan.keep_workspaces)
        if interrupted.is_set() or rec.get("agent_exit_code") in _CTRL_C_EXIT_CODES:
            # Ctrl-C reaches the agent processes too. A run cut short that way says nothing
            # about the agent, so it is not recorded and --resume runs it again.
            interrupted.set()
            return
        with lock:
            with runs_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
            done += 1
            if is_agent_error(rec) and not rec["passed"]:
                streak.append(rec)
            else:
                streak.clear()
            limit = plan.max_consecutive_errors
            if limit > 0 and len(streak) >= limit:
                stop.set()
        if progress:
            progress(rec)

    try:
        if plan.jobs <= 1:
            for job in jobs:
                if stop.is_set():
                    break
                _do(job)
        else:
            pool = ThreadPoolExecutor(max_workers=plan.jobs)
            try:
                futures = [pool.submit(_do, job) for job in jobs]
                for fut in futures:
                    fut.result()
            except KeyboardInterrupt:
                interrupted.set()
                raise
            finally:
                # On Ctrl-C, do not start the queued runs: each one is a paid agent session.
                stop.set()
                pool.shutdown(wait=True, cancel_futures=True)
    except KeyboardInterrupt:
        raise RunStopped(out_dir, "interrupted", done, len(jobs)) from None
    if interrupted.is_set():
        raise RunStopped(out_dir, "interrupted", done, len(jobs))
    if (
        stop.is_set()
        and plan.max_consecutive_errors > 0
        and len(streak) >= plan.max_consecutive_errors
    ):
        _set_aside(out_dir, streak)
        raise RunStopped(
            out_dir,
            f"{len(streak)} runs in a row ended in an agent error",
            done - len(streak),
            len(jobs),
            errors=streak,
        )
    return time.perf_counter() - t0


# Exit codes of a child process stopped by Ctrl-C: -SIGINT on POSIX (subprocess reports the
# signal as a negative code), 130 from a shell wrapper, STATUS_CONTROL_C_EXIT on Windows.
_CTRL_C_EXIT_CODES = frozenset({-2, 130, 0xC000013A})


def _set_aside(out_dir: Path, rows: list[dict]) -> None:
    """Move ``rows`` from ``runs.jsonl`` to ``errors.jsonl``."""
    keys = {(r["task_id"], r["run_index"]) for r in rows}
    runs_path = out_dir / "runs.jsonl"
    kept = [r for r in _read_runs(runs_path) if (r["task_id"], r["run_index"]) not in keys]
    runs_path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in kept), encoding="utf-8"
    )
    with (out_dir / "errors.jsonl").open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def pending_runs(out_dir: Path, plan: RunPlan) -> int:
    """How many of the plan's ``(task, run)`` pairs ``out_dir/runs.jsonl`` does not have."""
    runs_path = out_dir / "runs.jsonl"
    done = (
        {(r["task_id"], r["run_index"]) for r in _read_runs(runs_path)}
        if runs_path.is_file()
        else set()
    )
    return sum(1 for t in plan.tasks for i in range(plan.runs) if (t.id, i) not in done)


def _read_runs(runs_path: Path) -> list[dict]:
    """Parse ``runs.jsonl``, skipping blank or truncated lines (an interrupted write)."""
    rows = []
    for ln in runs_path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and "task_id" in row and "run_index" in row:
            rows.append(row)
    return rows


def load_results(path: Path) -> list[tuple[dict, list[dict]]]:
    """Find every ``meta.json`` + ``runs.jsonl`` pair under ``path`` (recursively)."""
    found = []
    metas = (
        [path / "meta.json"] if (path / "meta.json").is_file() else sorted(path.rglob("meta.json"))
    )
    for meta_path in metas:
        runs_path = meta_path.parent / "runs.jsonl"
        if not runs_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["_dir"] = str(meta_path.parent)
        found.append((meta, _read_runs(runs_path)))
    return found
