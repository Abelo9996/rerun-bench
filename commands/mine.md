---
description: Build rerun-bench tasks from a repo's own past bug-fix commits and replay them to find flaky fixes
argument-hint: "[repo path or github url, default .] [runs per task, default 5]"
disable-model-invocation: true
allowed-tools: Bash(rerun-bench *) Bash(uvx rerun-bench *)
---

The user ran `/rerun-bench:mine`. Arguments: "$ARGUMENTS"

Run rerun-bench as `rerun-bench` if that command exists on PATH, otherwise as
`uvx rerun-bench` (needs uv, git and Python 3.11+; if `uvx` is missing, tell the user to
install uv from https://docs.astral.sh/uv/ and stop).

`mine` scans a git repository for past commits that fixed a bug and added or changed a
test, replays the top few as tasks against the user's agent, and leads with the flip:
which of their own past fixes the agent reproduces reliably and which it flakes on.

Take the repo from the first argument (default `.`, the current directory) and the runs
per task from the second (default 5). First build the tasks only, so the user sees what
was mined before anything is spent:

```
rerun-bench mine <repo> --no-run
```

Show the user what it mined and what it skipped and why. A replay against a real agent
(default `claude`) spends the user's money or quota and asks for `--yes` first. Run it
once in confirm mode so it prints the number of agent sessions and a rough token and
dollar estimate rather than starting:

```
rerun-bench mine <repo> --runs <runs> --agent claude
```

Show that estimate to the user and get their explicit go-ahead. Only after they agree,
re-run the same command with the confirmation flag added (and `--card mine-card.svg` for a
shareable image). Do not start a real agent run before the user agrees.

Then read back the flip-first report: the per-task `passed N/M` line, any flaky task (with
its passing and failing run side by side), and the aggregate pass^k, flip rate and cost.
If no fix flips, say so plainly; do not invent a flip. The card is SVG; for X or Bluesky
the user converts it to PNG with `rsvg-convert`.

For a single test the user keeps seeing flake on:
`rerun-bench from-test <repo> <path/to/test_file.py> --runs <runs> --agent claude`.
