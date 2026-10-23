---
name: rerun-bench
description: Measure how consistent a coding agent is across repeated runs, either on a repo's own past bug-fix commits (rerun-bench mine) or on the bundled task suite. Run it on Claude Code, Codex CLI, opencode, or the free mock agent, read its reports, and add new tasks. Use this whenever the user wants to measure how reliable or flaky a coding agent or model is, replay their own past fixes against their agent, compare agents or CLI versions on pass^k, flip rate or cost variance, produce a rerun-bench report or card, or write a new task, even if they only say "benchmark my agent", "how flaky is this model" or "does my agent reproduce my own bug fixes".
---

# rerun-bench

rerun-bench runs each task N times per agent and reports pass rate, pass^k (all k runs pass),
flip rate (two runs disagree) and cost spread. Pass or fail is decided only by each task's
hidden `verify.py`. Tasks come from one of two places: a repo's own past bug-fix commits
(`mine`), or the bundled suite (`run`).

Invoke it as `rerun-bench ...` if installed, otherwise
`uvx rerun-bench ...`. Install this skill
with `npx skills add Abelo9996/rerun-bench`.

## From the user's own repo (the one-call path)

`rerun-bench mine <repo>` scans a git repository for past commits that fixed a bug and added
or changed a test, replays the top few as tasks against the user's agent, and leads with the
flip: which of the user's own past fixes the agent reproduces reliably and which it flakes on.
`<repo>` is a local path, a git URL, or `owner/repo` on GitHub.

1. Build the tasks only first, so the user sees what was mined before anything is spent:
   `rerun-bench mine . --no-run`. It prints what it mined and what it skipped and why
   (no test, test did not fail on the parent, missing deps). Nothing is replayable unless a
   commit changed source and a test that failed before the change and passes after.
2. Then a real run (default agent `claude`), gated by `--yes` like `run`:
   `rerun-bench mine . --runs 5 --agent claude --yes --card mine-card.svg`.
   Run once without `--yes` first to show the cost estimate and get a go-ahead.
3. For one test the user keeps seeing flake on:
   `rerun-bench from-test <repo> path/to/test_file.py --runs 5 --agent claude`.

The report leads with per-task `passed N/M`, then shows each flaky task's passing and failing
run side by side (diff, failing test output, wall time, tokens), then the aggregate. If no fix
flips, it says so; do not invent a flip.

## Run the bundled suite

1. Start with the mock agent. It is free and confirms the setup works:
   `rerun-bench run --agent mock --tasks all --runs 5 --out results/`
2. Real agents (`claude`, `codex`, `opencode`) spend the user's money or quota and refuse to
   start without `--yes`. Run the command once without `--yes`: it prints the number of agent
   sessions and a rough token and dollar estimate. Show that to the user and get their
   explicit go-ahead before adding `--yes`. Suggest a small first run such as
   `--tasks edit-config --runs 1`.
   `rerun-bench run --agent claude --model sonnet --runs 5 --out results/ --yes`
3. Report on everything under a results root:
   `rerun-bench report results/ --format md` (or `text`, `html -o report.html`, or `json`).
   For a 1200x630 image to post (X, Bluesky, a pull request):
   `rerun-bench card results/ -o rerun-bench-card.svg`. It is SVG only; for X or Bluesky the
   user converts it to PNG (`rsvg-convert`, or a browser screenshot). The card's sentence
   never names a winner; do not add one when you share it.
4. If `run` exits with code 4, several runs in a row ended in an agent error (not logged in,
   out of quota, rate limited). Show the user the printed error; after it is fixed, run the
   printed `--resume` command. Exit code 130 means the run was interrupted; the printed
   `--resume` command continues it.

Use at least 5 runs per task; with fewer, pass^k and flip rate are too noisy to compare.
Compare agents on the same task set and the same `--runs`.

## Read the report

- Prefer pass^k and flip rate over pass@k when the question is reliability. pass@k rewards
  an agent that succeeds once in k tries.
- Overlapping Wilson intervals mean the pass-rate difference is not established; the report
  says so in its Comparison section. Do not call one agent better when it does. The JSON
  report also has `macro_pass_rate_task_bootstrap_ci95`, which accounts for task sampling.
- Check the report's notes for agent errors. Runs that failed because of login, quota or rate
  limits measure the setup, not the agent.
- CV columns are within-task spread (std / mean across reruns of one task), averaged.
- `n/a` cost means the CLI did not report it (Codex reports tokens only unless prices are
  passed with `--agent-opt usd_per_mtok_in=... --agent-opt usd_per_mtok_out=...`).
- Per-run diffs are in `<result>/diffs/<task>/runNNN.diff`; failing verifier output is in
  `runs.jsonl` under `verify_output_tail`.

Formulas: `docs/METRICS.md` in the repository.

## Add a task

Create `tasks/<id>/` with:

- `task.toml`: `id` (equal to the directory name), `title`, `prompt`, `timeout`, `tags`.
- `workspace/`: starting files the agent sees.
- `verify.py`: stdlib-only Python, run with cwd set to the agent's workspace; exit 0 means
  pass. Keep it outside `workspace/` so the agent cannot read or edit it.
- `solution/`: reference files overlaid on `workspace/`.

The verifier must be deterministic and offline, because any variance it adds is
indistinguishable from agent variance. Check behavior by running code rather than matching
source text. Then validate:

```sh
uv run rerun-bench --tasks-dir tasks verify-tasks --tasks <id> -v   # must print "ok"
uv run pytest                                                      # in a repo checkout
```

`ok` means the untouched workspace fails and the reference solution passes. If the task
targets a failure mode (over-editing, ignoring AGENTS.md, weak tests), also add a test that
a plausible wrong answer fails. Full rules: `CONTRIBUTING.md`.
