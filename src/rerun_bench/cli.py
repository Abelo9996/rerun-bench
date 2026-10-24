"""CLI: ``rerun-bench mine | from-test | list | run | report | card | verify-tasks``."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, star, taskgen
from . import card as card_mod
from . import report as report_mod
from . import tasks as tasks_mod
from . import workspace as ws
from .adapters import ADAPTERS, get_adapter
from .runner import RunPlan, RunStopped, check_resumable, pending_runs, run_benchmark


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
    print("Free first run: rerun-bench run --agent mock --runs 5 --out results/")
    return 0


# Rough per-run usage measured in the 2026-10-03 pilot (docs/pilot-2026-10-03): median total
# tokens per run and, where the CLI reports it, median cost with the CLI's default model.
PILOT_PER_RUN = {"claude": (52_000, 0.0886), "codex": (56_600, None)}


def _cost_gate_message(args, adapter, n_tasks: int, n_runs: int) -> str:
    runs = "run" if n_runs == 1 else "runs"
    resuming = getattr(args, "resume", False)
    lines = [
        f"This starts {n_runs} {runs} of the real `{adapter.binary}` CLI"
        + (f" ({n_tasks} tasks x {args.runs} each)." if not resuming else " (resuming)."),
        "Each run is a full agent session with file-edit and shell permissions, inside a",
        "temp copy of the task workspace. It spends your API credit or plan quota.",
    ]
    est = PILOT_PER_RUN.get(args.agent)
    if est:
        tokens, usd = est
        line = f"Rough guide: one run used about {tokens:,} tokens in the 2026-10-03 pilot"
        if usd is not None:
            line += f" (${usd:.2f} with the default model)"
        line += f", so about {tokens * n_runs:,} tokens"
        if usd is not None:
            line += f" (${usd * n_runs:.2f})"
        line += " here."
        lines += _wrap_plain(line)
        lines.append("Your model, plan and tasks may differ.")
    if n_runs > 2 and not resuming and getattr(args, "cmd", None) == "run":
        lines.append("To try a single run first: --tasks edit-config --runs 1")
    return "\n".join(lines)


def _wrap_plain(text: str) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=80, break_on_hyphens=False)


def _rerun_command(args, run_id: str) -> str:
    """The command that continues ``run_id``, built from the options of this run."""
    parts = ["rerun-bench"]
    if args.tasks_dir:
        parts += ["--tasks-dir", args.tasks_dir]
    parts += ["run", "--agent", args.agent]
    if args.model:
        parts += ["--model", args.model]
    parts += ["--tasks", args.tasks, "--runs", str(args.runs), "--out", args.out]
    parts += ["--run-id", run_id]
    for opt in args.agent_opt:
        parts += ["--agent-opt", opt]
    if args.jobs != 1:
        parts += ["--jobs", str(args.jobs)]
    if args.seed:
        parts += ["--seed", str(args.seed)]
    if ADAPTERS[args.agent].real:
        parts.append("--yes")
    parts.append("--resume")
    return _join(parts)


def _join(parts: list[str]) -> str:
    """Quote a command line for the user's shell (cmd.exe or PowerShell on Windows)."""
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return " ".join(shlex.quote(p) for p in parts)


def cmd_run(args) -> int:
    selected = tasks_mod.select(_tasks(args), args.tasks)
    if not selected:
        print(
            f"error: --tasks {args.tasks!r} matched no tasks; see `rerun-bench list`",
            file=sys.stderr,
        )
        return 2
    if args.runs < 1:
        print("error: --runs must be >= 1", file=sys.stderr)
        return 2
    if args.resume and not args.run_id:
        print(
            "error: --resume needs --run-id naming the run to continue "
            "(the directory name under --out)",
            file=sys.stderr,
        )
        return 2
    out_root = Path(args.out)
    if args.run_id and (out_root / args.run_id).exists() and not args.resume:
        print(
            f"error: {out_root / args.run_id} already exists (add --resume to continue it, "
            "or pick another --run-id)",
            file=sys.stderr,
        )
        return 2
    adapter = get_adapter(args.agent, args.model, _parse_opts(args.agent_opt))
    plan = RunPlan(
        tasks=selected,
        runs=args.runs,
        seed=args.seed,
        jobs=args.jobs,
        keep_workspaces=args.keep_workspaces,
        max_consecutive_errors=args.max_consecutive_errors,
    )
    total = len(selected) * args.runs
    if args.resume and (out_root / args.run_id / "meta.json").is_file():
        try:
            check_resumable(out_root / args.run_id, adapter)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        total = pending_runs(out_root / args.run_id, plan)
        if total == 0:
            print(f"{out_root / args.run_id} already has every planned run; nothing to do.")
            if not args.no_report:
                _print_summary(out_root / args.run_id, args)
            return 0
    if adapter.real:
        if not adapter.available():
            print(
                f"error: `{adapter.binary}` is not on PATH. Install the {args.agent} CLI, "
                f"or point to it with --agent-opt bin=/path/to/{adapter.binary}.",
                file=sys.stderr,
            )
            return 2
        print(_cost_gate_message(args, adapter, len(selected), total), file=sys.stderr)
        if not args.yes:
            print("Re-run with --yes to start.", file=sys.stderr)
            return 3
        print(file=sys.stderr)
    elif not args.quiet:
        print("mock agent: simulated runs, nothing is spent. Cost and time below are made up.")
    done = 0

    def progress(rec: dict) -> None:
        nonlocal done
        done += 1
        if not args.quiet:
            status = "pass" if rec["passed"] else "FAIL"
            cost = rec.get("cost_usd")
            cost_s = f"${cost:.4f}" if cost is not None else "cost n/a"
            line = (
                f"[{done:>{len(str(total))}}/{total}] {rec['task_id']} run {rec['run_index']}: "
                f"{status}  {rec['wall_time_s']:.1f}s  {cost_s}"
            )
            if rec.get("agent_timed_out"):
                line += "  (timed out)"
            elif rec.get("agent_error"):
                line += f"\n      agent error: {rec['agent_error'][:120]}"
            print(line, flush=True)

    try:
        out_dir = run_benchmark(
            adapter,
            plan,
            out_root,
            run_id=args.run_id,
            progress=progress,
            resume=args.resume,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RunStopped as stop:
        resume_cmd = _rerun_command(args, stop.out_dir.name)
        if stop.reason == "interrupted":
            print(
                f"\ninterrupted: {done} of {total} runs recorded in {stop.out_dir}",
                file=sys.stderr,
            )
            print(f"Continue later with:\n  {resume_cmd}", file=sys.stderr)
            return 130
        last = stop.errors[-1].get("agent_error") if stop.errors else None
        print(f"\nstopped: {stop.reason}.", file=sys.stderr)
        if last:
            print(f"Last error: {last}", file=sys.stderr)
        print(
            "\n".join(
                _wrap_plain(
                    "This usually means the agent CLI is not logged in, out of quota, or rate "
                    "limited, so further runs would only record failures that are not the "
                    f"agent's. Those runs were moved to {stop.out_dir / 'errors.jsonl'} and are "
                    "not scored. Fix the problem (try the agent CLI by hand), then continue with:"
                )
            ),
            file=sys.stderr,
        )
        print(f"  {resume_cmd}", file=sys.stderr)
        print(
            "If these errors are a real result, rerun with --max-consecutive-errors 0.",
            file=sys.stderr,
        )
        return 4
    print(f"\nwrote {out_dir}")
    if not args.no_report:
        _print_summary(out_dir, args)
        if not args.quiet:
            star.maybe_show()
    return 0


def _print_summary(out_dir: Path, args) -> None:
    rep = report_mod.build(out_dir)
    print()
    print(report_mod.to_text(rep, per_task=False).rstrip())
    print()
    print("Next:")
    print(f"  {_join(['rerun-bench', 'report', str(out_dir)])}")
    print("      per-task detail for this run")
    print(
        f"  {_join(['rerun-bench', 'report', args.out, '--format', 'html', '-o', 'report.html'])}"
    )
    print(f"      one shareable page with every result set under {args.out}")


def _make_progress(args, total: int):
    done = 0

    def progress(rec: dict) -> None:
        nonlocal done
        done += 1
        if getattr(args, "quiet", False):
            return
        status = "pass" if rec["passed"] else "FAIL"
        cost = rec.get("cost_usd")
        cost_s = f"${cost:.4f}" if cost is not None else "cost n/a"
        line = (
            f"[{done:>{len(str(total))}}/{total}] {rec['task_id']} run {rec['run_index']}: "
            f"{status}  {rec['wall_time_s']:.1f}s  {cost_s}"
        )
        if rec.get("agent_timed_out"):
            line += "  (timed out)"
        elif rec.get("agent_error"):
            line += f"\n      agent error: {rec['agent_error'][:120]}"
        print(line, file=sys.stderr, flush=True)

    return progress


def _run_tasks_and_flip(args, adapter, selected, out_root: Path) -> int:
    """Shared tail of ``mine`` and ``from-test``: cost gate, run, flip-first report, card."""
    plan = RunPlan(
        tasks=selected,
        runs=args.runs,
        seed=args.seed,
        jobs=args.jobs,
        max_consecutive_errors=args.max_consecutive_errors,
    )
    total = len(selected) * args.runs
    if adapter.real:
        if not adapter.available():
            print(
                f"error: `{adapter.binary}` is not on PATH. Install the {args.agent} CLI, "
                f"or point to it with --agent-opt bin=/path/to/{adapter.binary}.",
                file=sys.stderr,
            )
            return 2
        print(_cost_gate_message(args, adapter, len(selected), total), file=sys.stderr)
        if not args.yes:
            print("Re-run with --yes to start.", file=sys.stderr)
            return 3
        print(file=sys.stderr)
    elif not args.quiet:
        print(
            "mock agent: simulated runs, nothing is spent. Cost and time below are made up.",
            file=sys.stderr,
        )
    try:
        out_dir = run_benchmark(adapter, plan, out_root, progress=_make_progress(args, total))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RunStopped as stop:
        print(f"\nstopped: {stop.reason}. Recorded runs are in {stop.out_dir}", file=sys.stderr)
        return 4
    print(f"\nwrote {out_dir}", file=sys.stderr)
    sys.stdout.write(report_mod.to_flip_text(out_dir, k=args.k))
    if getattr(args, "card", None):
        _write_mined_card(out_dir, Path(args.card), args.k)
    if not args.quiet:
        star.maybe_show()
    return 0


def _write_mined_card(out_dir: Path, card_path: Path, k: int | None) -> None:
    if card_path.suffix.lower() != ".svg":
        card_path = card_path.with_suffix(".svg")
    rep = report_mod.build(out_dir, k=k)
    model = card_mod.card_model(rep, mined=True)
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(card_mod.render_svg(model), encoding="utf-8")
    print(f"wrote {card_path} (1200x630 SVG): {model['sentence']}", file=sys.stderr)


def cmd_mine(args) -> int:
    from . import mine_cmd

    tasks_dir = Path(args.tasks_out).expanduser().resolve()
    try:
        outcome = mine_cmd.mine_tasks(
            args.repo,
            tasks_dir,
            want=args.max,
            history=args.history,
            hide_tests=args.hide_tests,
            test_timeout=args.test_timeout,
            keep_scratch=args.keep_clone,
        )
    except mine_cmd.MineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        for line in mine_cmd.summarize(outcome):
            print(line, file=sys.stderr)
        built_ids = [tid for tid, _ in outcome.built]
        if args.no_run:
            print(file=sys.stderr)
            print(f"Built {len(built_ids)} task(s) under {tasks_dir}.", file=sys.stderr)
            print(
                f"Run them with:\n  rerun-bench --tasks-dir {tasks_dir} run --agent {args.agent} "
                f"--runs {args.runs} --out {args.out} --yes",
                file=sys.stderr,
            )
            return 0
        selected = tasks_mod.select(tasks_mod.discover(tasks_dir), ",".join(built_ids))
        adapter = get_adapter(args.agent, args.model, _parse_opts(args.agent_opt))
        print(file=sys.stderr)
        return _run_tasks_and_flip(args, adapter, selected, Path(args.out))
    finally:
        if not args.keep_clone:
            outcome.cleanup()


def cmd_from_test(args) -> int:
    import tempfile

    from . import mine_cmd
    from .mining import MineError, is_git_repo

    repo = Path(args.repo).expanduser()
    if not is_git_repo(repo):
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 2
    repo = repo.resolve()
    tasks_dir = Path(args.tasks_out).expanduser().resolve()
    scratch = Path(tempfile.mkdtemp(prefix="rerun-bench-fromtest-"))
    try:
        cand, prepared = mine_cmd.from_test_candidate(
            repo, args.test_id, args.commit, scratch, args.test_timeout
        )
        if not cand.verified:
            print(
                f"error: {args.test_id} does not replay from {cand.short}: {cand.skip_reason}",
                file=sys.stderr,
            )
            return 2
        tasks_dir.mkdir(parents=True, exist_ok=True)
        root = taskgen.build_task(
            repo, cand, tasks_dir, hide_tests=args.hide_tests, prepared=prepared
        )
        print(f"built {root.name} from {cand.short}: {cand.subject[:60]}", file=sys.stderr)
        if args.no_run:
            print(
                f"Run it with:\n  rerun-bench --tasks-dir {tasks_dir} run --agent {args.agent} "
                f"--runs {args.runs} --out {args.out} --yes",
                file=sys.stderr,
            )
            return 0
        selected = tasks_mod.select(tasks_mod.discover(tasks_dir), root.name)
        adapter = get_adapter(args.agent, args.model, _parse_opts(args.agent_opt))
        print(file=sys.stderr)
        return _run_tasks_and_flip(args, adapter, selected, Path(args.out))
    except MineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if not args.keep_clone:
            shutil.rmtree(scratch, ignore_errors=True)


def cmd_report(args) -> int:
    path = Path(args.results)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2
    if args.k is not None and args.k < 1:
        print("error: --k must be >= 1", file=sys.stderr)
        return 2
    rep = report_mod.build(path, k=args.k)
    if not rep["entries"]:
        print(
            f"error: no runs found under {path}. A result set is a directory with meta.json "
            "and a non-empty runs.jsonl, written by `rerun-bench run --out <dir>`.",
            file=sys.stderr,
        )
        return 2
    fmt = args.format
    if fmt is None:
        fmt = "text" if (not args.output and sys.stdout.isatty()) else "md"
    text = report_mod.RENDERERS[fmt](rep)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    if fmt != "json":
        star.maybe_show()
    return 0


def cmd_card(args) -> int:
    path = Path(args.results)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2
    if args.k is not None and args.k < 1:
        print("error: --k must be >= 1", file=sys.stderr)
        return 2
    out = Path(args.output)
    if out.suffix.lower() != ".svg":
        if out.suffix.lower() == ".png":
            print(
                "error: PNG output is not built in (it would need an image library). Write the "
                f"SVG with -o {out.with_suffix('.svg')}, then convert it, for example:\n"
                f"  rsvg-convert -o {out} {out.with_suffix('.svg')}",
                file=sys.stderr,
            )
        else:
            print(f"error: -o must end in .svg, got {str(out)!r}", file=sys.stderr)
        return 2
    if path.is_file() and path.suffix.lower() == ".json":
        try:
            rep = card_mod.from_report_json(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            print(f"error: {path} is not a rerun-bench JSON report ({exc})", file=sys.stderr)
            return 2
    else:
        rep = report_mod.build(path, k=args.k)
    if not rep["entries"]:
        print(
            f"error: no runs found under {path}. A result set is a directory with meta.json "
            "and a non-empty runs.jsonl, written by `rerun-bench run --out <dir>`.",
            file=sys.stderr,
        )
        return 2
    model = card_mod.card_model(rep)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(card_mod.render_svg(model), encoding="utf-8")
    print(f"wrote {out} (1200x630 SVG): {model['sentence']}.")
    if model["more"]:
        print(
            f"The card shows {card_mod.MAX_ROWS} result sets; {model['more']} more are not shown."
        )
    print(
        "X and Bluesky need a PNG. Convert with rsvg-convert (brew install librsvg, or apt "
        f"install librsvg2-bin):\n  rsvg-convert -o {out.with_suffix('.png')} {out}\n"
        "or open the SVG in a browser and take a screenshot of the card."
    )
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


def _add_mine_build_args(s) -> None:
    s.add_argument(
        "--tasks-out",
        default="rerun-bench-tasks",
        help="where to write the built tasks (default ./rerun-bench-tasks)",
    )
    s.add_argument(
        "--hide-tests",
        action="store_true",
        help="keep the test out of the workspace the agent sees (checked only by the verifier)",
    )
    s.add_argument(
        "--test-timeout",
        type=int,
        default=120,
        help="seconds to allow each test run while mining (default 120)",
    )
    s.add_argument("--keep-clone", action="store_true", help="keep the scratch clone and worktrees")
    s.add_argument("--no-run", action="store_true", help="only build the tasks, do not run them")


def _add_agent_run_args(s) -> None:
    s.add_argument("--agent", default="claude", choices=sorted(ADAPTERS), help="default claude")
    s.add_argument("--model", help="model passed to the agent CLI (default: the CLI's default)")
    s.add_argument("--runs", type=int, default=5, help="runs per task (default 5)")
    s.add_argument("--out", default="results", help="results root directory (default results/)")
    s.add_argument("--seed", type=int, default=0, help="seed for the mock agent (default 0)")
    s.add_argument("--jobs", type=int, default=1, help="parallel runs (default 1)")
    s.add_argument("--k", type=int, help="k for pass@k and pass^k (default: runs per task)")
    s.add_argument(
        "--card", help="also write a shareable 1200x630 SVG card to this path", metavar="PATH"
    )
    s.add_argument(
        "--agent-opt", action="append", default=[], metavar="KEY=VALUE", help="adapter option"
    )
    s.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=3,
        metavar="N",
        help="stop after N agent errors in a row (default 3, 0 = never)",
    )
    s.add_argument("--yes", action="store_true", help="confirm a run against a real agent")
    s.add_argument("--quiet", action="store_true", help="no per-run progress lines")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rerun-bench",
        description="Run the same coding tasks N times per agent and report pass rate, "
        "consistency across reruns, and cost spread.",
        epilog="Start free with the mock agent:\n"
        "  rerun-bench run --agent mock --runs 5 --out results/\n"
        "  rerun-bench report results/ --format html -o report.html\n"
        "Then a small real run (asks for --yes first):\n"
        "  rerun-bench run --agent claude --tasks edit-config --runs 1 --out results/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    s.add_argument(
        "--tasks", default="all", help="'all' (default), comma-separated ids, or tag:<name>"
    )
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
    s.add_argument(
        "--resume",
        action="store_true",
        help="continue the --run-id directory, running only the task/run pairs it lacks",
    )
    s.add_argument("--yes", action="store_true", help="confirm a run against a real agent")
    s.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=3,
        metavar="N",
        help="stop after N runs in a row end in an agent error such as a login or quota "
        "failure (default 3, 0 = never stop)",
    )
    s.add_argument("--quiet", action="store_true", help="no per-run progress lines")
    s.add_argument("--no-report", action="store_true", help="skip the summary at the end")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser(
        "mine",
        help="build and run tasks from a repo's own past bug-fix commits",
        description="Scan a git repository for past commits that fixed a bug and added or "
        "changed a test, replay the top few as tasks against your agent, and lead the report "
        "with the flip (which fixes the agent reproduces reliably, which it flakes).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("repo", help="a local git repo path, a git URL, or owner/repo on GitHub")
    s.add_argument("-n", "--max", type=int, default=3, help="how many tasks to build (default 3)")
    s.add_argument(
        "--history", type=int, default=200, help="how many commits to scan (default 200)"
    )
    _add_mine_build_args(s)
    _add_agent_run_args(s)
    s.set_defaults(func=cmd_mine)

    s = sub.add_parser(
        "from-test",
        help="build and run one task from the commit that last changed a test",
        description="Build a single task from the commit that added or changed a test, for "
        "'my agent keeps flaking on this test'. Replays that fix against your agent --runs "
        "times and leads with the flip.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("repo", help="a local git repository path")
    s.add_argument("test_id", help="repo-relative path to the test file (optionally file::name)")
    s.add_argument("--commit", help="use this commit instead of the last one that changed the test")
    _add_mine_build_args(s)
    _add_agent_run_args(s)
    s.set_defaults(func=cmd_from_test)

    s = sub.add_parser(
        "report",
        help="summarize one or more result directories",
        description="Summarize every result set under a directory.",
    )
    s.add_argument("results", help="a result directory or a root containing several")
    s.add_argument(
        "--format",
        choices=sorted(report_mod.RENDERERS),
        help="text (default in a terminal), md (default when piped or with -o), "
        "html (one self-contained page) or json",
    )
    s.add_argument("-o", "--output", help="write to a file instead of stdout")
    s.add_argument("--k", type=int, help="k for pass@k and pass^k (default: runs per task)")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser(
        "card",
        help="write a 1200x630 SVG result card to post",
        description="Write a 1200x630 SVG card (the size X, Bluesky and link previews use) "
        "with the pass rate and its 95%% interval, pass^k, flip rate and median cost of every "
        "result set under a directory.",
    )
    s.add_argument(
        "results",
        help="a result directory, a root containing several, or a report saved with --format json",
    )
    s.add_argument(
        "-o", "--output", default="rerun-bench-card.svg", help="output file (default %(default)s)"
    )
    s.add_argument("--k", type=int, help="k for pass^k (default: runs per task)")
    s.set_defaults(func=cmd_card)

    s = sub.add_parser(
        "verify-tasks", help="check that each task fails untouched and passes with its solution"
    )
    s.add_argument(
        "--tasks", default="all", help="'all' (default), comma-separated ids, or tag:<name>"
    )
    s.add_argument("-v", "--verbose", action="store_true", help="show verifier output for failures")
    s.set_defaults(func=cmd_verify_tasks)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except tasks_mod.TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
