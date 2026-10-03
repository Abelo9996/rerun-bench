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
- `codex` runs pass `--ignore-user-config` by default (`--agent-opt isolate=0` to disable),
  so a personal `config.toml` (model, effort, plugins, notify hooks) does not leak into the
  measurement.
- Recorded verifier output has the workspace, task and home directory paths replaced with
  `<workspace>`, `<task>` and `~`, so result directories can be published as they are.

### Added

- `run --resume` continues an interrupted `--run-id`, running only the missing task and run
  pairs. A truncated last line in `runs.jsonl` is dropped instead of breaking the report.
- `--agent-opt bin=<path>` runs a specific build of an agent CLI.
- `--agent-opt effort=<level>` for `claude` (`--effort`) and `codex`
  (`model_reasoning_effort`).
- Run records include `agent_stdout_tail` and `agent_stderr_tail` (paths scrubbed), so a
  run that fails without changing anything can be diagnosed from the result files.
- Pilot results for Claude Code and Codex CLI in `docs/pilot-2026-10-03/`.
- JSON report: `median_cost_usd`, `tokens_median`, `output_tokens_median` and
  `wall_time_total_s`.

### Fixed

- `claude`: tokens are summed over every model in `modelUsage`, so they cover the same
  calls as `total_cost_usd`; previously only the main conversation's `usage` was counted and
  subagent or background-model tokens were missed.
- `claude`: when started from inside a Claude Code session, the parent session's
  environment variables (`CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_EFFORT` and
  others) are no longer inherited by the measured session.
- `codex`: transient `error` events that Codex retries ("Reconnecting... 2/5") no longer
  mark a successful run as an error; only `turn.failed`, or errors with no completed turn,
  do.
- `codex`: `cache_write_input_tokens` (Codex CLI 0.160) is read and split out of input
  tokens instead of being counted as uncached input.
- `codex`: a cached-token price of `0` is no longer replaced by the input price.

## 0.1.0 - 2026-10-03

- First release.
- `rerun-bench list`, `run`, `report` (md, html, json) and `verify-tasks` commands.
- Adapters: `claude`, `codex`, `opencode`, and a deterministic, seeded `mock`.
- Ten offline, deterministic tasks with hidden verifiers and reference solutions.
- Metrics: pass rate with Wilson and task-bootstrap intervals, pass@k, pass^k, flip rate,
  flaky task fraction, cost, token and wall-time spread (within-task CV), cost per success,
  and approach similarity of passing diffs.
- Self-contained static HTML report.
