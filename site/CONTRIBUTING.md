# Contributing

Two kinds of data are welcome: result sets from rerun-bench, and regression reports from
nerf-watch. Code changes to the site are welcome too; keep the build dependency-free.

## Submitting results

Open a pull request that adds one file to `data/results/`.

### File

- Name: `data/results/<YYYY-MM-DD>-<label>.json`. The date is the UTC day the runs started.
  The label is lowercase letters, digits and hyphens, for example `claude-2-1-288-n5`.
- Content: the output of `rerun-bench report <results dir> --format json`, unedited apart
  from the optional `lab` block below.
- One result set per file. Each entry inside it is one agent, model and CLI version.

### Required metadata (in the pull request description)

- Agent CLI and exact version for each entry (`<cli> --version`).
- Model, and how it was selected (flag, config, or CLI default).
- rerun-bench version and commit.
- Runs per task (at least 3) and the exact `rerun-bench run` commands.
- Machine: OS, CPU architecture, Python version.
- Authentication type (API key or subscription login), because it changes what reported
  cost means.
- Whether agents ran concurrently, and the `--jobs` value.
- Any non-default isolation or `--agent-opt` settings.
- A link to the raw run records (`meta.json`, `runs.jsonl`, diffs), for example a branch or
  release in your fork of rerun-bench. Results without run records are not merged.
- Any failure you investigated, and whether it was the agent, the task or the environment.

### The lab block

Optional. Add it at the top level of the JSON file:

```json
"lab": {
  "title": "Claude Code 2.1.288 vs Codex CLI 0.160.0, 10 tasks x 5 runs",
  "pilot": false,
  "date": "2026-10-03",
  "source_url": "https://github.com/<you>/rerun-bench/tree/<branch>/results",
  "harness_commit": "7a2bef2",
  "machine": "macOS 26.2, Apple Silicon (arm64), Python 3.13.15",
  "launch": "gpt-6-luna",
  "notes": ["One sentence per note. Plain facts about the run."]
}
```

| Field | Meaning |
|---|---|
| `title` | Heading for the result set. Defaults to the date and label. |
| `pilot` | `true` shows a "Pilot, n=N per task" badge. Use it for runs meant to test the setup. |
| `date` | Must equal the date in the file name. |
| `source_url` | HTTPS link to run records and diffs. |
| `harness_commit` | rerun-bench commit hash. |
| `machine` | Where the runs happened. |
| `launch` | Set for launch-day result sets: the model that launched. |
| `notes` | Facts a reader needs: cost semantics, failures and their causes, deviations. |

### Checks

```sh
npm run validate
npm test
npm run build
```

CI runs the same checks on every pull request. The validator rejects files whose numbers
contradict each other (for example a pass rate outside its own interval, or per-run outcomes
that do not add up to the pass count).

### Review

A maintainer checks the run records against the report, reruns the report from
`runs.jsonl` with the stated rerun-bench version, and confirms the metadata. Copy is kept
factual: no claims beyond what the numbers show.

## Submitting a regression report

1. Run `npx nerf-watch share`. It prints the anonymized JSON that would be shared and a
   link to a prefilled [regression report](https://github.com/Abelo9996/open-agent-lab/issues/new?template=regression-report.yml).
   Add `--open` to open the link in your browser.
2. Read the JSON. It holds only detector ids, severities, agent, model ids, CLI versions,
   dates, sample counts and before and after values.
3. Open the link, describe what you observed, and submit. If the JSON was too long for the
   link, paste it into the report field yourself.

### How reports are aggregated

The `regressions` workflow (`.github/workflows/regressions.yml`) runs daily, on manual
dispatch, and whenever an issue with the `regression-report` label is opened, edited,
closed, reopened, deleted or relabeled. It:

1. reads open issues with that label through the GitHub API, with a read-only issues token;
2. takes the first JSON code block in each body and validates it strictly
   (`scripts/lib/regressions.mjs`): exact keys, known detectors and signals, anchored
   patterns for agent ids, versions and model ids, bounded sizes and numbers, valid dates,
   and no path-like, email-like, URL-like or markup text anywhere. Anything else is skipped
   and the log names the issue number and the reason, never its content;
3. groups findings by agent, CLI version (the first version showing the change), model and
   signal, and counts independent reports as distinct GitHub accounts (one account's newest
   issue per row). Each row has the median effect size, the dates the change was seen, and
   links to the source issues;
4. writes `aggregates` in `data/regressions.json`, commits only if it changed, and the pages
   workflow publishes it.

Closing an issue, or removing its label, removes it at the next run. Run the aggregator
locally against saved API output with
`node scripts/aggregate-regressions.mjs --issues issues.json --out /tmp/regressions.json`.

Effect sizes by signal: ratios (after divided by before) for tokens, cache writes and
context window; percentage-point changes for cache hit rate and tool error rate; levels for
reasoning effort; the share of turns answered by another model for model rerouting.

### Reviewed reports

Maintainers can also add hand-reviewed entries to `reports` in `data/regressions.json`. The
aggregator keeps them as they are. Each has one of these statuses:

| Status | Meaning |
|---|---|
| `open` | Reviewed, plausible, not yet confirmed. |
| `confirmed` | Matched by independent reports or reproduced with rerun-bench. |
| `not-reproduced` | Could not be reproduced and no matching reports arrived. |
| `explained` | Caused by a documented change (release notes, settings, plan change). |

```json
{
  "id": "claude-2-1-272-cache-writes",
  "reported_at": "2026-10-03",
  "agent": "claude",
  "model": "claude-opus-5",
  "cli_before": "2.1.271",
  "cli_after": "2.1.272",
  "signal": "cache-writes",
  "summary": "Median cache writes per call rose from 926 to 3,037 after the update.",
  "independent_reports": 1,
  "status": "open",
  "issue_url": "https://github.com/Abelo9996/open-agent-lab/issues/1"
}
```

`signal` is one of `model-reroute`, `effort-drop`, `context-shrink`, `cache-writes`,
`cache-hit-rate`, `tool-errors`, `tokens`, `cost`, `pass-rate`, `other`. `agent` must be an id
in `data/agents.json`.

## Adding an agent

Add an entry to `data/agents.json` with an `id` matching the `agent` field rerun-bench writes,
a display `name`, and an HTTPS `homepage` or `null`.

## Writing style

Plain, specific, factual. No superlatives, no rankings where intervals overlap, no claims
beyond the data. Use hyphens or commas, not long dashes.
