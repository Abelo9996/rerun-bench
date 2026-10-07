# rerun-bench

English | [简体中文](README.zh-CN.md)

[![CI](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

**Does a coding agent pass the same task every time you rerun it?** In 200 runs on 2026-10-06
(10 tasks, 10 runs each), Claude Code 2.1.292 with claude-opus-5-5 passed 100 of 100 and Codex
CLI 0.160.0 with gpt-6-luna passed 96 of 100. All 4 Codex failures were the same: it read the
file, changed nothing and exited cleanly, and in 3 of them its final message said it had made
the change. The pass-rate intervals still overlap ([96, 100] vs [90, 98]), so the runs do not
establish a difference in overall pass rate; they do show what a single run would have hidden.
Setup, raw run records and diffs: [docs/run-2026-10-06](docs/run-2026-10-06/README.md).

[![Result card for the 2026-10-06 run. The 95% intervals of Claude Code and Codex CLI overlap, so these runs do not establish a difference in pass rate. Claude Code with claude-opus-5-5: pass rate 100% [96, 100], pass^10 100%, flip rate 0%, median cost $0.0899 per run. Codex CLI with gpt-6-luna: pass rate 96% [90, 98], pass^10 70%, flip rate 8%, cost not reported. 10 tasks, 10 runs each, 200 runs in all.](https://raw.githubusercontent.com/Abelo9996/rerun-bench/main/docs/run-2026-10-06/card.png)](https://github.com/Abelo9996/rerun-bench/tree/main/docs/run-2026-10-06)

```sh
uvx rerun-bench run --agent mock --runs 5     # free demo: simulated agent, no API key, about 30 s
uvx rerun-bench run --agent claude --runs 3   # real agent (or codex, opencode): shows the cost first, add --yes to start
```

Also available as a [Claude Code plugin](#install-as-a-claude-code-plugin), a
[Codex plugin](#install-as-a-codex-plugin), a [GitHub Action](#use-in-ci)
(`uses: Abelo9996/rerun-bench@v0`), and with Homebrew (`brew install abelo9996/tap/rerun-bench`).

![rerun-bench running the free mock agent 5 times on each of 10 tasks, then printing each task's pass and fail sequence, pass rate, flip rate and cost spread](docs/demo.gif)

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
uvx rerun-bench list
uvx rerun-bench run --agent mock --tasks all --runs 5 --out results/
uvx rerun-bench report results/ --format html -o report.html
```

The `run` command ends with a short summary and the next commands to try; `report.html` is
one self-contained page you can open or share. Mock runs are labeled simulated: their cost,
tokens and wall time are made up. Or install once with `uv tool install rerun-bench` (or
`pipx install rerun-bench`) and drop the `uvx` prefix.

Homebrew (macOS and Linux): `brew install abelo9996/tap/rerun-bench`, then run `rerun-bench list` without `uvx`.

After the first report you see in a terminal, rerun-bench prints one line asking for a GitHub
star, once per machine, and records that in your user state directory. It never prints it in
CI, when output is piped, or for `--format json`, and it sends nothing over the network. Turn
it off with `RERUN_BENCH_NO_STAR_PROMPT=1`.

## Install as a Claude Code plugin

Inside Claude Code:

```text
/plugin marketplace add Abelo9996/open-agent-lab
/plugin install rerun-bench@open-agent-lab
```

Then run `/reload-plugins` or start a new session. The plugin adds the rerun-bench skill and two
commands: `/rerun-bench:run-mock [runs] [dir]` runs the suite with the free mock agent and
summarizes it, and `/rerun-bench:report [dir]` summarizes results or writes a report with
`--format html -o report.html`. Both run the CLI through `uvx rerun-bench`, so you need
[uv](https://docs.astral.sh/uv/) and nothing else. Neither command starts a paid agent run. From
a shell: `claude plugin marketplace add Abelo9996/open-agent-lab`, then
`claude plugin install rerun-bench@open-agent-lab`.

## Install as a Codex plugin

```sh
codex plugin marketplace add Abelo9996/open-agent-lab
codex plugin add rerun-bench@open-agent-lab
```

This adds the rerun-bench skill to Codex, so "benchmark how consistent this agent is" runs the
suite (mock first, real agents only after you confirm the cost) and reads the report.

## Run real agents

Supported CLIs, each driven headlessly in a fresh temporary copy of the task workspace:

| Agent | Command rerun-bench runs | Cost reported by the CLI |
|---|---|---|
| `claude` (Claude Code) | `claude -p <prompt> --output-format json --permission-mode bypassPermissions --no-session-persistence` | yes (`total_cost_usd`) |
| `codex` (OpenAI Codex CLI) | `codex exec --json --skip-git-repo-check --ephemeral --sandbox workspace-write --cd <ws> --ignore-user-config <prompt>` | tokens only; pass prices with `--agent-opt` to get dollars |
| `opencode` | `opencode run --format json <prompt>` | yes (per step) |

```sh
rerun-bench run --agent claude --model sonnet --tasks all --runs 5 --out results/ --yes
rerun-bench run --agent codex --model <model> --runs 5 --out results/ --yes \
  --agent-opt usd_per_mtok_in=1.25 --agent-opt usd_per_mtok_out=10 --agent-opt usd_per_mtok_cached=0.125
rerun-bench report results/ --format md
```

The `usd_per_mtok_*` values are placeholders; use the published prices of the model you run.

Each run records wall time, exit status, token usage and cost (when the CLI reports them),
the CLI version, the model, and the final diff. A value the CLI does not report is stored as
`null`, never as zero.

**Cost warning.** Real runs spend your API credit or subscription quota: a full suite at
`--runs 5` is 50 agent sessions. rerun-bench refuses to start a real agent without `--yes`. It
first prints the number of runs and a rough token and dollar estimate based on the pilot below
(about 52,000 tokens and $0.09 per Claude Code run with its default model; your model may
cost more or less). Start with `--tasks edit-config --runs 1`. The agent runs with file-edit
and shell permissions inside a temp directory; treat it like any other unattended agent
session.

**Setup failures stop the run.** If 3 runs in a row end in an agent error (non-zero exit, or an
error the CLI reports, such as not logged in, out of quota or rate limited), rerun-bench stops,
prints the agent's error, moves those runs to `errors.jsonl` so they are not scored, and prints
the `--resume` command to continue once the problem is fixed. `--max-consecutive-errors 0`
turns this off. Agent errors that do not stop the run still count as fails, and every report
says how many there were.

Personal configuration is kept out of the measurement by default. For `claude`, rerun-bench
loads only project and local settings and ignores MCP servers outside `--mcp-config`, so your
hooks, plugins and MCP servers do not apply. For `codex`, it passes `--ignore-user-config`, so
the model, reasoning effort, plugins and notify hooks in your `config.toml` do not apply (auth
still works). `--agent-opt isolate=0` turns this off for either agent. When rerun-bench itself
runs inside a Claude Code session, that session's environment variables (`CLAUDECODE`,
`CLAUDE_CODE_SESSION_ID` and similar) are removed before starting the measured `claude`.

`codex exec --json` does not report which model it ran, so pass `--model` if you want the
model recorded; otherwise the report shows `default`.

Other useful flags: `--jobs 4` (parallel runs), `--tasks tag:refactor` or `--tasks a,b`,
`--keep-workspaces` (inspect what the agent left behind), `--seed` (mock only),
`--agent-opt bin=/path/to/cli` (run a specific build of the CLI), `--agent-opt effort=high`
(`claude --effort` or Codex `model_reasoning_effort`).

Long runs can be interrupted and continued. Ctrl-C stops the run, keeps every finished run,
and prints the exact command to continue. `--resume` with the same `--run-id` runs only the
task and run pairs that `runs.jsonl` does not have yet.

```sh
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude-pilot --yes
# interrupted; later:
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude-pilot --yes --resume
```

## Use in CI

The repository is also a GitHub Action. It runs the benchmark, uploads the result set and the
report as artifacts, writes the text summary to the job summary, and exposes the headline
numbers as outputs. The default agent is `mock`, so it works with no setup and spends nothing.

```yaml
# .github/workflows/rerun-bench.yml
name: rerun-bench
on: [pull_request, workflow_dispatch]
permissions:
  contents: read
jobs:
  mock:
    runs-on: ubuntu-latest
    steps:
      - id: bench
        uses: Abelo9996/rerun-bench@v0
        with:
          runs: 5
      - env:
          PASS_RATE: ${{ steps.bench.outputs.pass-rate }}
          LOW: ${{ steps.bench.outputs.pass-rate-low }}
          HIGH: ${{ steps.bench.outputs.pass-rate-high }}
        run: echo "pass rate $PASS_RATE, 95% interval $LOW to $HIGH"
```

A fuller file with a real-agent job that only runs when started by hand is in
[examples/rerun-bench.yml](examples/rerun-bench.yml).

| Input | Default | Meaning |
|---|---|---|
| `agent` | `mock` | `mock`, `claude`, `codex` or `opencode`. |
| `tasks` | `all` | `all`, comma-separated ids, or `tag:<name>`. |
| `runs` | `5` | Runs per task. |
| `tasks-dir` | | A task suite in your repository (check it out first). Empty means the bundled suite. |
| `version` | `0.2.0` | rerun-bench version from PyPI, run with `uvx`. A path to a checkout also works. |
| `extra-args` | | More `rerun-bench run` flags, split on whitespace, e.g. `--model sonnet --jobs 2`. |
| `report-format` | `html` | Format of the report artifact: `html`, `md`, `json` or `text`. |
| `results-dir` | `rerun-bench-results` | Where the result set is written. |
| `artifact-name` | `rerun-bench` | Artifacts are `<name>-results` and `<name>-report`. Set a unique value when the action runs more than once in a workflow run (for example in a matrix). |

Outputs, as fractions (0.8 means 80%): `pass-rate`, `pass-rate-low` and `pass-rate-high` (the
95% Wilson interval), `flip-rate` (empty with 1 run per task) and `pass-hat-k`; plus `k`,
`runs`, `passes`, `agent-errors`, `run-dir` and `report-path`. A later step can gate on them, for
example fail when `pass-rate-low` is under a threshold.

**Real agents in CI cost money.** Every run is a full agent session billed to the key or plan
you provide; the defaults (10 tasks, 5 runs) are 50 sessions, about $4.40 with Claude Code's
default model in the pilot below. The action passes `--yes`, so there is no prompt. Install
the agent's CLI in an earlier step and pass its credentials as `env` on the action step:

| `agent` | Install step | Credentials (`env` on the action step) |
|---|---|---|
| `mock` | none | none |
| `claude` | `npm install -g @anthropic-ai/claude-code` | `ANTHROPIC_API_KEY` (Claude Console key, billed per token), or `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (your Claude plan). With `--agent-opt bare=1` only `ANTHROPIC_API_KEY` works. |
| `codex` | `npm install -g @openai/codex` | `CODEX_API_KEY` (an OpenAI API key; `codex exec` reads it). |
| `opencode` | `npm install -g opencode-ai` | The API key variable of the provider in `--model provider/model`, for example `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. |

The agent runs with shell access in the job, so it can read any variable in its environment.
Use a key with a spending limit, set it only on the action step (not for the whole job), and do
not run real agents on events that untrusted people can trigger. Secrets are not passed to
workflows started from forks.

## Results

### 2026-10-06: 10 runs per task

All 10 tasks, 10 runs each, on the same Mac as the pilot: Claude Code 2.1.292 pinned to
`claude-opus-5-5`, Codex CLI 0.160.0 (`gpt-6-luna`), and Claude Code with no model flag, which
on this account now reports `claude-opus-4-8`. Full setup, the failures, raw run records and
diffs: [docs/run-2026-10-06](docs/run-2026-10-06/README.md).

| Agent / model | Pass rate [Wilson 95% CI] | pass^10 | Flip rate | Median cost/run | Median tokens/run | Median wall time |
|---|---|---|---|---|---|---|
| claude / claude-opus-5-5 | 100/100, 100% [96, 100] | 100% | 0% | $0.0899 | 53,368 | 12.7 s |
| codex / gpt-6-luna | 96/100, 96% [90, 98] | 70% | 8% | not reported | 56,552 | 16.8 s |
| claude / default (claude-opus-4-8) | 100/100, 100% [96, 100] | 100% | 0% | $0.1312 | 84,534 | 15.6 s |

The pass-rate intervals overlap, so these runs do not establish a difference in overall pass
rate. All 4 Codex failures were clean exits after 7 to 10 seconds with no file changed; in 3 of
them the final message said the change had been made.

### 2026-10-03: pilot

A first run against real CLIs on 2026-10-03: all 10 tasks, 3 runs each, Claude Code 2.1.288
(default model, reported as `claude-opus-5-5`) and Codex CLI 0.160.0 (`gpt-6-luna`), on
macOS arm64. Full setup, per-task outcomes, raw run records and diffs:
[docs/pilot-2026-10-03](docs/pilot-2026-10-03/README.md).

| Agent / model | Pass rate [Wilson 95% CI] | pass^3 | Flip rate | Median cost/run | Median tokens/run | Median wall time |
|---|---|---|---|---|---|---|
| claude / claude-opus-5-5 | 30/30, 100% [89, 100] | 100% | 0% | $0.0886 | 52,017 | 12.6 s |
| codex / gpt-6-luna | 28/30, 93% [79, 98] | 80% | 13% | not reported | 56,629 | 16.1 s |

n = 3 per task is a pilot, not a leaderboard. The pass-rate intervals overlap, so these
runs do not establish a difference between the two agents. Claude Code's cost is its own
list-price estimate; Codex reports tokens only.

![rerun-bench result card for the 2026-10-03 pilot: the 95% intervals of Claude Code and Codex CLI overlap, so these runs do not establish a difference in pass rate. Claude Code 100% [89, 100], pass^3 100%, flip rate 0%, median cost $0.0886 per run; Codex CLI 93% [79, 98], pass^3 80%, flip rate 13%, cost not reported. 10 tasks, 3 runs each.](docs/pilot-2026-10-03/card.svg)

## Share card

`rerun-bench card` turns a results directory into a 1200x630 SVG, the size X, Bluesky and
link previews use, like the one above:

```sh
uvx rerun-bench card results/                       # writes rerun-bench-card.svg
uvx rerun-bench card results/ -o my-card.svg --k 3
uvx rerun-bench card report.json                    # from a report saved with --format json
```

It shows each result set's pass rate with its 95% interval drawn as a bar with whiskers on a
shared 0 to 100% axis, pass^k, flip rate, median cost per run, the number of tasks and runs,
and the date. The headline is one plain sentence about the comparison, with the same rule as
the report: when the intervals overlap it says the runs do not establish a difference, and
when they do not overlap it says only that. Rows are in name order, not ranked. Mock results
are marked simulated. The card uses system fonts and follows light or dark mode where the
viewer supports it.

The output is SVG only, so rerun-bench stays dependency free. X and Bluesky need a PNG:
`rsvg-convert -o card.png rerun-bench-card.svg` (librsvg: `brew install librsvg` or
`apt install librsvg2-bin`), or open the SVG in a browser and take a screenshot.

## Example report

Two mock profiles, 10 tasks, 5 runs each. Free to reproduce:

```sh
uvx rerun-bench run --agent mock --model mock-steady --agent-opt pass_prob=0.85 \
  --agent-opt token_cv=0.15 --runs 5 --out results/
uvx rerun-bench run --agent mock --model mock-flaky --agent-opt pass_prob=0.6 \
  --agent-opt token_cv=0.5 --runs 5 --out results/
uvx rerun-bench report results/
```

In a terminal, `report` prints an 80-column summary (excerpt):

```
mock / mock-steady  [mock 0.2.0]
  Pass rate     80%  [67, 89]   40 of 50 runs passed
  pass^5        30%  all 5 reruns of a task pass
  pass@5       100%  at least 1 of 5 reruns passes
  Flip rate     34%  two runs of the same task disagree
  Flaky tasks   70%  tasks with both passes and fails
  Cost/run     $0.0582 median, $0.0597 mean, CV 0.14 (simulated)

mock / mock-flaky  [mock 0.2.0]
  Pass rate     60%  [46, 72]   30 of 50 runs passed
  pass^5         0%  all 5 reruns of a task pass
  pass@5       100%  at least 1 of 5 reruns passes
  Flip rate     50%  two runs of the same task disagree
  Flaky tasks  100%  tasks with both passes and fails
  Cost/run     $0.0551 median, $0.0609 mean, CV 0.35 (simulated)

Comparison
  The pass-rate 95% intervals of all rows overlap, so these runs are not enough
  to tell the rows apart. More runs per task narrow the intervals.
  ...
  Rows are sorted by pass^5, then pass rate. The order is not a ranking.

Per task: runs in order (P pass, F fail), pass rate
  task                     A            B
  add-cli-flag             PPPPP 100%   PPPFP  80%
  fix-failing-test         FPPPP  80%   FFFPF  20%
  ...
```

Both profiles reach pass@5 = 100%: given five tries, each solves every task at least once.
Their pass-rate intervals overlap, so the pass rate alone does not separate them; pass^5 and
the flip rate show how differently they behave from one rerun to the next. The report never
names a winner: when the intervals overlap it says so, and when they do not it states only
that. `--format md` gives Markdown tables for a README or pull request, `--format json` every
number, and `--format html` one static page with inline CSS and JS: a short "how to read
this" key, sortable tables, and a per-task grid of run outcomes.

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
| Agent errors, timeouts | Runs that ended in a non-zero exit, a CLI-reported error, or the task timeout. Counted as fails and listed in every report. |

Only the task's verifier decides pass or fail. The agent's exit code and its own claims of
success are recorded but not scored. When several result sets are in one report, pass@k and
pass^k use the same k for every row: the smallest runs per task among them (`--k` to lower it).

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

Then check it from the repository root: `uv run rerun-bench --tasks-dir tasks verify-tasks
--tasks my-task -v` must print `ok` (the untouched workspace fails, the reference solution
passes), and `uv run pytest` picks the new task up automatically. To run your own task suite
outside a checkout, pass `--tasks-dir <path>` before the subcommand:
`uvx rerun-bench --tasks-dir my-tasks run --agent mock --runs 3`. Rules for verifiers are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Add an adapter

Subclass `Adapter` in `src/rerun_bench/adapters/`, implement two pure methods, and register it
in `ADAPTERS` in `src/rerun_bench/adapters/__init__.py`:

```python
# src/rerun_bench/adapters/myagent.py
import json
from pathlib import Path

from .base import Adapter, Usage


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

The base class handles the subprocess, timeout, wall time, `--version`, and turning a non-zero
exit into a recorded agent error. Every adapter except `mock` is treated as a paid agent, so
`run` asks for `--yes` before starting it. Test both methods against a captured sample of the
CLI's output (see `tests/test_adapters.py`); the test suite never calls a real agent.

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
