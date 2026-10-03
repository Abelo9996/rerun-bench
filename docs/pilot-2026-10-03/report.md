# rerun-bench report

Generated 2026-10-03T08:26:33+00:00 by rerun-bench 0.1.0. k = runs per task. CV columns are the mean within-task coefficient of variation. Definitions: docs/METRICS.md.

## Leaderboard

| Agent / model | CLI version | Runs/task | Pass rate [95% CI] | pass@k | pass^k | Flip rate | Flaky tasks | Cost/run | Cost CV | Tokens CV | Wall median | Wall CV | Approach sim. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude / claude-opus-5-5 | 2.1.288 (Claude Code) | 3 | 100% [89, 100] | 100% | 100% | 0% | 0% | $0.0938 | 0.05 | 0.04 | 12.6s | 0.18 | 0.81 |
| codex / gpt-6-luna | codex-cli 0.160.0 | 3 | 93% [79, 98] | 100% | 80% | 13% | 20% | n/a | n/a | 0.14 | 16.1s | 0.21 | 0.77 |

## Per-task consistency

Outcomes in run order (P = pass, F = fail), then pass rate, flip rate, and cost CV.

| Task | claude / claude-opus-5-5 | codex / gpt-6-luna |
|---|---|---|
| add-cli-flag | `PPP` 100%, flip 0%, cost CV 0.13 | `PPP` 100%, flip 0%, cost CV n/a |
| edit-config | `PPP` 100%, flip 0%, cost CV 0.07 | `PPP` 100%, flip 0%, cost CV n/a |
| fix-failing-test | `PPP` 100%, flip 0%, cost CV 0.01 | `PPP` 100%, flip 0%, cost CV n/a |
| follow-agents-md | `PPP` 100%, flip 0%, cost CV 0.02 | `PPP` 100%, flip 0%, cost CV n/a |
| implement-lru-cache | `PPP` 100%, flip 0%, cost CV 0.06 | `FPP` 67%, flip 67%, cost CV n/a |
| implement-slugify | `PPP` 100%, flip 0%, cost CV 0.03 | `PPP` 100%, flip 0%, cost CV n/a |
| minimal-fix | `PPP` 100%, flip 0%, cost CV 0.01 | `PPP` 100%, flip 0%, cost CV n/a |
| multi-file-rename | `PPP` 100%, flip 0%, cost CV 0.02 | `PPP` 100%, flip 0%, cost CV n/a |
| refactor-extract-helper | `PPP` 100%, flip 0%, cost CV 0.05 | `PFP` 67%, flip 67%, cost CV n/a |
| write-tests | `PPP` 100%, flip 0%, cost CV 0.12 | `PPP` 100%, flip 0%, cost CV n/a |
