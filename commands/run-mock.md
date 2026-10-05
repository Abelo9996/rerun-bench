---
description: Run the rerun-bench task suite with the free mock agent to check the setup, then summarize the report
argument-hint: "[runs per task, default 5] [output dir, default rerun-bench-results/]"
disable-model-invocation: true
allowed-tools: Bash(rerun-bench *) Bash(uvx rerun-bench *)
---

The user ran `/rerun-bench:run-mock`. Arguments: "$ARGUMENTS"

Run rerun-bench as `rerun-bench` if that command exists on PATH, otherwise as
`uvx rerun-bench` (needs uv and Python 3.11+; if `uvx` is missing, tell the user to
install uv from https://docs.astral.sh/uv/ and stop).

The mock agent is free: it spends no money or quota and makes no network calls, and
its costs, tokens and times are simulated. Take the number of runs per task from
the first argument (default 5) and the output directory from the second (default
`rerun-bench-results/`), then run:

```
rerun-bench run --agent mock --tasks all --runs <runs> --out <dir>
rerun-bench report <dir> --format md
```

Summarize in a few lines: pass rate with its 95% interval, pass^k, flip rate and the
share of flaky tasks, and say plainly that these numbers describe the simulated mock
agent, not a real one. Then give the next steps the run printed: an HTML report
(`rerun-bench report <dir> --format html -o report.html`) and a small real run such
as `rerun-bench run --agent claude --tasks edit-config --runs 1 --out <dir>`, which
spends the user's quota and asks for `--yes` first. Do not start a real agent run
from this command.
