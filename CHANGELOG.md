# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## 0.1.1 - Unreleased

### Fixed

- A relative `--tasks-dir` (for example `--tasks-dir tasks`, as the README showed) made every
  verifier fail to start, so every run scored as a fail. Task paths are now absolute.
- Agent setup failures (not logged in, out of quota, rate limited) were scored as ordinary
  fails with no visible sign. A non-zero exit or a CLI-reported error is now recorded in
  `agent_error` with the agent's own message, shown on the progress line, and counted in every
  report. After 3 such runs in a row, `run` stops, moves them to `errors.jsonl` so they are
  not scored, and prints the `--resume` command (`--max-consecutive-errors` to change or
  disable).
- Ctrl-C printed a traceback. It now keeps the finished runs and prints the exact `--resume`
  command, including the generated run id. With `--jobs` above 1, queued runs no longer start
  after Ctrl-C, and runs cut short by it are not recorded.
- A newly added adapter could start a paid agent without `--yes` and without checking that its
  binary exists. Every adapter except `mock` now goes through the same gate.
- `--resume` on a finished run with a different agent or model now fails instead of silently
  doing nothing; the `--yes` prompt counts only the runs that are left.
- `--k 0` or a negative `--k` crashed the report; it is now rejected. A missing or empty
  `--tasks-dir`, or an unknown task id in `verify-tasks`, gives an error instead of a traceback.

### Changed

- Reports compare rows honestly: pass@k and pass^k use the same k for every row (the smallest
  runs per task), a Comparison section says whether the pass-rate intervals overlap, and no
  report names a winner. Rows are labeled as sorted, not ranked.
- New `--format text`, an 80-column terminal report with a one-line meaning per metric. It is
  the default when `report` writes to a terminal; piped output and `-o` stay Markdown.
- `run` ends with that summary and the next commands to try, instead of a 14-column table.
- Markdown and HTML reports split the leaderboard into a reliability table and a cost and
  spread table, start with a short "how to read this" key, and list notes the reader needs
  (agent errors, timeouts, incomplete runs, simulated mock data, unreported cost). The HTML
  report no longer scrolls sideways on a phone.
- The `--yes` prompt gives a rough token and dollar estimate from the 2026-10-03 pilot and
  suggests a single-run first try.
- Missing agent CLI: the error says how to point at it with `--agent-opt bin=`.

## 0.1.0 - 2026-10-03

First release on PyPI.

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

### Initial features

- First release.
- `rerun-bench list`, `run`, `report` (md, html, json) and `verify-tasks` commands.
- Adapters: `claude`, `codex`, `opencode`, and a deterministic, seeded `mock`.
- Ten offline, deterministic tasks with hidden verifiers and reference solutions.
- Metrics: pass rate with Wilson and task-bootstrap intervals, pass@k, pass^k, flip rate,
  flaky task fraction, cost, token and wall-time spread (within-task CV), cost per success,
  and approach similarity of passing diffs.
- Self-contained static HTML report.
