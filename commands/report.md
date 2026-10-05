---
description: Summarize rerun-bench results (pass rate, pass^k, flip rate, cost spread), or write a Markdown or HTML report
argument-hint: "[results dir, default rerun-bench-results/] [--format md|html|json|text] [-o file]"
disable-model-invocation: true
allowed-tools: Bash(rerun-bench *) Bash(uvx rerun-bench *)
---

The user ran `/rerun-bench:report`. Arguments: "$ARGUMENTS"

Run rerun-bench as `rerun-bench` if that command exists on PATH, otherwise as
`uvx rerun-bench`. The first argument is the results directory; with none, use
`rerun-bench-results/` if it exists, otherwise `results/`. If neither exists, say so
and suggest `/rerun-bench:run-mock`.

- If the arguments include `--format` or `-o`, run
  `rerun-bench report $ARGUMENTS` as given and tell the user where the file went.
- Otherwise run `rerun-bench report <dir> --format md` and summarize it.

When you summarize, for each agent and model give the runs per task, the pass rate
with its 95% interval, pass^k, pass@k, flip rate and median cost. Prefer pass^k and
flip rate when the question is reliability. If two agents' intervals overlap, say the
difference is not established; do not call one better. Point out notes about agent
errors (login, quota, rate limits), which measure the setup rather than the agent,
and that `n/a` cost means the CLI did not report it.
