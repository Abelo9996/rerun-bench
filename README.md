# rerun-bench

[![CI](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

Run the same coding task N times per agent and find out how often it succeeds, how often it
flips between pass and fail, and how much the bill varies from run to run.

Most coding-agent benchmarks (SWE-bench, Terminal-Bench and its harbor harness) report a
success rate from one attempt per task. That number hides what you live with day to day: the
agent that fixed the bug on Monday fails the same task on Tuesday, at twice the token cost.
rerun-bench runs a fixed suite of small, verifiable tasks several times per agent, model and CLI
version, then reports reliability (pass^k, flip rate) and cost spread (coefficient of
variation) next to the pass rate.

## Quickstart (free, about 30 seconds)

The `mock` adapter simulates an agent with a configurable pass probability and token usage. It
spends nothing and needs no API key, so you can see the whole pipeline before pointing it at a
paid agent.

```sh
uvx --from git+https://github.com/Abelo9996/rerun-bench rerun-bench list
uvx --from git+https://github.com/Abelo9996/rerun-bench rerun-bench run --agent mock --tasks all --runs 5 --out results/
uvx --from git+https://github.com/Abelo9996/rerun-bench rerun-bench report results/ --format html -o report.html
```

Or install once with `uv tool install git+https://github.com/Abelo9996/rerun-bench` and drop
the `uvx --from ...` prefix.

## Run real agents

Supported CLIs, each driven headlessly in a fresh temporary copy of the task workspace:

| Agent | Command rerun-bench runs | Cost reported by the CLI |
|---|---|---|
| `claude` (Claude Code) | `claude -p <prompt> --output-format json --permission-mode bypassPermissions` | yes (`total_cost_usd`) |
| `codex` (OpenAI Codex CLI) | `codex exec --json --sandbox workspace-write --cd <ws> <prompt>` | tokens only; pass prices with `--agent-opt` to get dollars |
| `opencode` | `opencode run --format json <prompt>` | yes (per step) |

```sh
rerun-bench run --agent claude --model sonnet --tasks all --runs 5 --out results/ --yes
rerun-bench run --agent codex --model gpt-5-codex --runs 5 --out results/ --yes \
  --agent-opt usd_per_mtok_in=1.25 --agent-opt usd_per_mtok_out=10 --agent-opt usd_per_mtok_cached=0.125
rerun-bench report results/ --format md
```

Each run records wall time, exit status, token usage and cost (when the CLI reports them),
the CLI version, the model, and the final diff. A value the CLI does not report is stored as
`null`, never as zero.

**Cost warning.** Real runs spend your API credit or subscription quota: a full suite at
`--runs 5` is 50 agent sessions. rerun-bench refuses to start a real agent without `--yes`, and
prints the run count first. Start with `--tasks edit-config --runs 2`. The agent runs with
file-edit and shell permissions inside a temp directory; treat it like any other unattended
agent session.

For `claude`, rerun-bench by default loads only project and local settings and ignores MCP
servers outside `--mcp-config`, so your personal hooks and MCP servers do not change the
measurement. `--agent-opt isolate=0` turns that off.

Other useful flags: `--jobs 4` (parallel runs), `--tasks tag:refactor` or `--tasks a,b`,
`--keep-workspaces` (inspect what the agent left behind), `--seed` (mock only).

## Example report

Two mock profiles, 10 tasks, 5 runs each (`rerun-bench report results/`):

| Agent / model | Runs/task | Pass rate [95% CI] | pass@k | pass^k | Flip rate | Flaky tasks | Cost/run | Cost CV |
|---|---|---|---|---|---|---|---|---|
| mock / mock-steady | 5 | 86% [74, 93] | 100% | 40% | 26% | 60% | $0.0601 | 0.19 |
| mock / mock-flaky | 5 | 60% [46, 72] | 100% | 0% | 50% | 100% | $0.0906 | 0.46 |

| Task | mock / mock-steady | mock / mock-flaky |
|---|---|---|
| fix-failing-test | `PPPPP` 100%, flip 0%, cost CV 0.13 | `FFFPF` 20%, flip 40%, cost CV 0.49 |
| minimal-fix | `PPPPF` 80%, flip 40%, cost CV 0.16 | `PPFPF` 60%, flip 60%, cost CV 0.46 |

Both profiles reach pass@5 = 100%: given five tries, each solves every task at least once.
Only pass^5 and the flip rate separate them. The HTML report (`--format html`) is one static
file with inline CSS and JS, a sortable leaderboard, and a per-task grid of run outcomes.

## Metrics

Full definitions, estimators and caveats: [docs/METRICS.md](docs/METRICS.md).

| Metric | What it answers |
|---|---|
| Pass rate + Wilson 95% CI | How often does a run pass the hidden verifier? |
| Task-bootstrap 95% CI | Same, with uncertainty over which tasks were sampled (JSON report). |
| pass@k | Chance that at least one of k runs passes (unbiased estimator). |
| pass^k | Chance that all k runs pass. The number to watch if you run once and trust the result. |
| Flip rate | Chance that two runs of the same task disagree, 2c(n-c)/(n(n-1)). |
| Flaky tasks | Share of tasks with both passes and fails. |
| Cost / tokens / wall-time CV | Run-to-run spread within a task (std / mean), averaged over tasks. |
| Cost per success | Total cost divided by passing runs. |
| Approach similarity | Mean pairwise Jaccard of changed lines among passing runs. 1.0 means the same edit every time. |

Only the task's verifier decides pass or fail. The agent's exit code and its own claims of
success are recorded but not scored.

## Task suite

`rerun-bench list` shows the bundled tasks:

| Task | What it tests |
|---|---|
| `fix-failing-test` | Fix the bug behind a failing unit test without editing the test |
| `implement-slugify` | Implement a function exactly to a docstring spec |
| `implement-lru-cache` | Implement a small data structure to spec |
| `refactor-extract-helper` | Extract duplicated logic; behavior checked on a grid of inputs |
| `follow-agents-md` | Add a function; the prompt does not mention the repo's AGENTS.md rules, the verifier checks them |
| `edit-config` | Three precise TOML edits; a production config next to it must stay untouched |
| `multi-file-rename` | Rename a function across a package, no alias left behind |
| `minimal-fix` | One-line bug in deliberately dated code; any cleanup outside the function fails |
| `add-cli-flag` | Add a flag without changing default output |
| `write-tests` | Write tests that pass on the real code and catch five injected bugs (mutation testing) |

Every task is offline, deterministic, and uses only the Python standard library, so it runs
the same on Linux, macOS and Windows.

## Add a task

```
tasks/<id>/
  task.toml      id, title, prompt, timeout (seconds), tags
  workspace/     the files the agent starts with
  verify.py      exit 0 = pass; runs with cwd = the agent's workspace; never shown to the agent
  solution/      reference solution, copied over workspace/ by the test suite
```

```toml
id = "my-task"
title = "One line describing the task"
prompt = """
What you would type to the agent.
"""
timeout = 600
tags = ["bugfix", "python"]
```

Then check it: `rerun-bench --tasks-dir tasks verify-tasks --tasks my-task -v` must print `ok`
(the untouched workspace fails, the reference solution passes), and `uv run pytest` picks the
new task up automatically. Rules for verifiers are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Add an adapter

Subclass `Adapter` in `src/rerun_bench/adapters/`, implement two pure methods, and register it
in `ADAPTERS` in `src/rerun_bench/adapters/__init__.py`:

```python
class MyAgentAdapter(Adapter):
    name = "myagent"
    binary = "myagent"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return [self.binary, "run", "--json", prompt]

    def parse_output(self, stdout: str, stderr: str) -> Usage:
        # Fill tokens, cost and model; leave a field None when the CLI does not report it.
        data = json.loads(stdout)
        return Usage(output_tokens=data.get("output_tokens"), cost_usd=data.get("cost"))
```

The base class handles the subprocess, timeout, wall time and `--version`. Test both methods
against a captured sample of the CLI's output (see `tests/test_adapters.py`); the test suite
never calls a real agent.

## Agent skill

`skills/rerun-bench/SKILL.md` teaches a coding agent to run the benchmark and add tasks:

```sh
npx skills add Abelo9996/rerun-bench
```

## Roadmap

- Public leaderboard, refreshed on model launch days, built from the HTML report.
- Version-over-version tracking: the same model under successive CLI releases, with
  per-task significance tests.
- Paired comparisons between two result sets (Fisher exact per task, task-level bootstrap
  for the suite).
- More tasks in other languages, kept small, offline and deterministic.
- Resume for interrupted runs.

## Related projects

- [nerf-watch](https://github.com/Abelo9996/nerf-watch): detects silent model and cost changes
  from your local agent logs.
- [snap-back](https://github.com/Abelo9996/snap-back): undo for any coding agent.

## Development

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run rerun-bench verify-tasks
```

MIT licensed. See [LICENSE](LICENSE).
