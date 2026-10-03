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
from .adapters import Adapter
from .adapters.mock import MockAdapter
from .tasks import Task, verify

SCHEMA_VERSION = 1


@dataclass
class RunPlan:
    tasks: list[Task]
    runs: int
    seed: int = 0
    jobs: int = 1
    keep_workspaces: bool = False


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "default"


def make_run_id(agent: str, model: str | None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{_slug(agent)}_{_slug(model or 'default')}_{now.strftime('%Y%m%dT%H%M%SZ')}"


def execute_one(adapter: Adapter, task: Task, run_index: int, seed: int, out_dir: Path,
                keep_workspace: bool = False) -> dict:
    work = ws.fresh_copy(task.workspace)
    pristine = ws.fresh_copy(task.workspace)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        if isinstance(adapter, MockAdapter):
            adapter.solution_dir = task.solution
        result = adapter.run(task.prompt, work, timeout=task.timeout, seed=seed,
                             run_key=f"{task.id}/{run_index}")
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
    files = sorted({ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/")}
                   | {ln[6:] for ln in diff.splitlines() if ln.startswith("--- a/")})
    u = result.usage
    return {
        "task_id": task.id,
        "run_index": run_index,
        "started_at": started,
        "passed": vres.passed,
        "verify_exit_code": vres.exit_code,
        "verify_timed_out": vres.timed_out,
        "verify_output_tail": vres.output[-1000:],
        "agent_exit_code": result.exit_code,
        "agent_timed_out": result.timed_out,
        "agent_error": result.error,
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


def run_benchmark(adapter: Adapter, plan: RunPlan, out_root: Path, run_id: str | None = None,
                  progress: Callable[[dict], None] | None = None) -> Path:
    """Run the plan and write ``<out_root>/<run_id>/{meta.json,runs.jsonl,diffs/}``.

    Runs are interleaved (run 0 of every task, then run 1, ...) so that drift over the
    session, such as rate limiting or a provider-side change, spreads across tasks instead
    of landing on whichever task happened to run last.
    """
    run_id = run_id or make_run_id(adapter.name, adapter.model)
    out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "rerunbench_version": __version__,
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
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    jobs = [(t, i) for i in range(plan.runs) for t in plan.tasks]
    lock = threading.Lock()
    runs_path = out_dir / "runs.jsonl"
    t0 = time.perf_counter()

    def _do(job: tuple[Task, int]) -> None:
        task, idx = job
        # Each worker gets its own adapter instance state for the mock's solution_dir.
        local = adapter if plan.jobs == 1 else type(adapter)(adapter.model, adapter.options)
        rec = execute_one(local, task, idx, plan.seed, out_dir, plan.keep_workspaces)
        with lock, runs_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        if progress:
            progress(rec)

    if plan.jobs <= 1:
        for job in jobs:
            _do(job)
    else:
        with ThreadPoolExecutor(max_workers=plan.jobs) as pool:
            list(pool.map(_do, jobs))
    meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    meta["elapsed_s"] = round(time.perf_counter() - t0, 3)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_dir


def load_results(path: Path) -> list[tuple[dict, list[dict]]]:
    """Find every ``meta.json`` + ``runs.jsonl`` pair under ``path`` (recursively)."""
    found = []
    metas = [path / "meta.json"] if (path / "meta.json").is_file() else sorted(
        path.rglob("meta.json"))
    for meta_path in metas:
        runs_path = meta_path.parent / "runs.jsonl"
        if not runs_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["_dir"] = str(meta_path.parent)
        runs = [json.loads(ln) for ln in runs_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()]
        found.append((meta, runs))
    return found
