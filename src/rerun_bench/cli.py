"""Command-line interface: ``rerun-bench list | run | report | verify-tasks``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from . import report as report_mod
from . import tasks as tasks_mod
from . import workspace as ws
from .adapters import ADAPTERS, REAL_AGENTS, get_adapter
from .runner import RunPlan, run_benchmark


def _parse_opts(pairs: list[str]) -> dict[str, str]:
    out = {}
    for p in pairs:
        if "=" not in p:
            raise SystemExit(f"--agent-opt expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _tasks(args) -> list[tasks_mod.Task]:
    root = Path(args.tasks_dir) if args.tasks_dir else None
    return tasks_mod.discover(root)


def cmd_list(args) -> int:
    tasks = _tasks(args)
    width = max((len(t.id) for t in tasks), default=4)
    for t in tasks:
        tags = ",".join(t.tags)
        print(f"{t.id:<{width}}  {t.timeout:>4}s  {t.title}  [{tags}]")
    print(f"\n{len(tasks)} tasks. Agents: {', '.join(sorted(ADAPTERS))}")
    return 0


def cmd_run(args) -> int:
    try:
        selected = tasks_mod.select(_tasks(args), args.tasks)
    except tasks_mod.TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not selected:
        print("error: no tasks selected", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("error: --runs must be >= 1", file=sys.stderr)
        return 2
    adapter = get_adapter(args.agent, args.model, _parse_opts(args.agent_opt))
    total = len(selected) * args.runs
    if args.agent in REAL_AGENTS:
        if not adapter.available():
            print(f"error: `{adapter.binary}` is not on PATH", file=sys.stderr)
            return 2
        print(
            f"warning: this runs the real `{adapter.binary}` CLI {total} times "
            f"({len(selected)} tasks x {args.runs} runs). It spends your model quota or API "
            "credit, and the agent runs with file-edit and shell permissions inside a temp "
            "copy of each task workspace.",
            file=sys.stderr,
        )
        if not args.yes:
            print("Re-run with --yes to confirm.", file=sys.stderr)
            return 3
    out_root = Path(args.out)
    done = 0

    def progress(rec: dict) -> None:
        nonlocal done
        done += 1
        if not args.quiet:
            status = "pass" if rec["passed"] else "FAIL"
            cost = rec.get("cost_usd")
            cost_s = f"${cost:.4f}" if cost is not None else "cost n/a"
            print(
                f"[{done:>{len(str(total))}}/{total}] {rec['task_id']} run {rec['run_index']}: "
                f"{status}  {rec['wall_time_s']:.1f}s  {cost_s}",
                flush=True,
            )

    if args.run_id and (out_root / args.run_id).exists():
        print(f"error: {out_root / args.run_id} already exists", file=sys.stderr)
        return 2
    out_dir = run_benchmark(
        adapter,
        RunPlan(
            tasks=selected,
            runs=args.runs,
            seed=args.seed,
            jobs=args.jobs,
            keep_workspaces=args.keep_workspaces,
        ),
        out_root,
        run_id=args.run_id,
        progress=progress,
    )
    print(f"\nwrote {out_dir}")
    if not args.no_report:
        rep = report_mod.build(out_dir)
        print()
        print(report_mod.to_markdown(rep).split("## Per-task")[0].rstrip())
    return 0


def cmd_report(args) -> int:
    path = Path(args.results)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2
    rep = report_mod.build(path, k=args.k)
    if not rep["entries"]:
        print(f"error: no result sets (meta.json + runs.jsonl) under {path}", file=sys.stderr)
        return 2
    text = report_mod.RENDERERS[args.format](rep)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_verify_tasks(args) -> int:
    """Check every task: untouched workspace must fail, reference solution must pass."""
    selected = tasks_mod.select(_tasks(args), args.tasks)
    bad = 0
    for t in selected:
        base = ws.fresh_copy(t.workspace)
        sol = ws.fresh_copy(t.workspace)
        try:
            r0 = tasks_mod.verify(t, base)
            if t.solution.is_dir():
                ws.overlay(t.solution, sol)
                r1 = tasks_mod.verify(t, sol)
            else:
                r1 = None
        finally:
            ws.cleanup(base)
            ws.cleanup(sol)
        ok = (not r0.passed) and r1 is not None and r1.passed
        bad += not ok
        print(
            f"{'ok  ' if ok else 'BAD '} {t.id}: untouched={'pass' if r0.passed else 'fail'} "
            f"solution={'missing' if r1 is None else ('pass' if r1.passed else 'fail')}"
        )
        if not ok and args.verbose:
            print((r1.output if r1 else r0.output).rstrip())
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rerun-bench",
        description="Run the same coding tasks N times per agent and report pass rate, "
        "consistency across reruns, and cost spread.",
    )
    p.add_argument("--version", action="version", version=f"rerun-bench {__version__}")
    p.add_argument("--tasks-dir", help="task suite directory (default: bundled suite)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="list tasks in the suite")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser(
        "run",
        help="run tasks N times with one agent",
        description="Run each selected task --runs times with one agent. Each run "
        "gets a fresh temp copy of the task workspace.",
    )
    s.add_argument("--agent", required=True, choices=sorted(ADAPTERS))
    s.add_argument("--model", help="model passed to the agent CLI (default: the CLI's default)")
    s.add_argument("--tasks", default="all", help="'all', comma-separated ids, or tag:<name>")
    s.add_argument("--runs", type=int, default=5, help="runs per task (default 5)")
    s.add_argument("--out", default="results", help="results root directory (default results/)")
    s.add_argument("--run-id", help="name of the result directory (default agent_model_time)")
    s.add_argument("--seed", type=int, default=0, help="seed for the mock agent (default 0)")
    s.add_argument("--jobs", type=int, default=1, help="parallel runs (default 1)")
    s.add_argument(
        "--agent-opt",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="adapter option, repeatable (e.g. pass_prob=0.6 for mock)",
    )
    s.add_argument("--keep-workspaces", action="store_true", help="keep per-run temp dirs")
    s.add_argument("--yes", action="store_true", help="confirm a run against a real agent")
    s.add_argument("--quiet", action="store_true")
    s.add_argument("--no-report", action="store_true", help="skip the summary at the end")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("report", help="summarize one or more result directories")
    s.add_argument("results", help="a result directory or a root containing several")
    s.add_argument("--format", choices=sorted(report_mod.RENDERERS), default="md")
    s.add_argument("-o", "--output", help="write to a file instead of stdout")
    s.add_argument("--k", type=int, help="k for pass@k and pass^k (default: runs per task)")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser(
        "verify-tasks", help="check that each task fails untouched and passes with its solution"
    )
    s.add_argument("--tasks", default="all")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_verify_tasks)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
