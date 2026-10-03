# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## Unreleased

## 0.1.0 - 2026-10-03

- First release.
- `rerunbench list`, `run`, `report` (md, html, json) and `verify-tasks` commands.
- Adapters: `claude`, `codex`, `opencode`, and a deterministic, seeded `mock`.
- Ten offline, deterministic tasks with hidden verifiers and reference solutions.
- Metrics: pass rate with Wilson and task-bootstrap intervals, pass@k, pass^k, flip rate,
  flaky task fraction, cost, token and wall-time spread (within-task CV), cost per success,
  and approach similarity of passing diffs.
- Self-contained static HTML report.
