# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## Unreleased

### Changed

- Renamed the project from `rerunbench` to `rerun-bench`. The repository is now
  github.com/Abelo9996/rerun-bench, the command is `rerun-bench`, the Python import package
  is `rerun_bench`, and the agent skill lives in `skills/rerun-bench/`. Environment
  variables are now `RERUN_BENCH_TASKS_DIR` and `RERUN_BENCH_TASK_DIR`, and result
  metadata records `rerun_bench_version`.

## 0.1.0 - 2026-10-03

- First release.
- `rerun-bench list`, `run`, `report` (md, html, json) and `verify-tasks` commands.
- Adapters: `claude`, `codex`, `opencode`, and a deterministic, seeded `mock`.
- Ten offline, deterministic tasks with hidden verifiers and reference solutions.
- Metrics: pass rate with Wilson and task-bootstrap intervals, pass@k, pass^k, flip rate,
  flaky task fraction, cost, token and wall-time spread (within-task CV), cost per success,
  and approach similarity of passing diffs.
- Self-contained static HTML report.
