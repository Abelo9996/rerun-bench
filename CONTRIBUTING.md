# Contributing

Thanks for helping. The most useful contributions are new tasks and new adapters.

## Setup

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Task authoring rules

A rerun-bench task measures an agent, so the task itself must contribute zero variance.

1. **Deterministic verifier.** `verify.py` must give the same answer every time for the same
   workspace. No randomness, no wall-clock checks, no dependence on dict or set iteration
   order, no timing thresholds. Set any seeds explicitly.
2. **Reference solution.** Ship `solution/` with the minimal files that make the task pass.
   The test suite overlays it on `workspace/` and requires the verifier to pass, and requires
   the untouched workspace to fail. Run `rerun-bench verify-tasks --tasks <id> -v`.
3. **No network.** Neither the task nor the verifier may need the network. Use only the
   Python standard library in `verify.py` so it runs under `uvx` with no extra installs.
4. **Hidden checks.** Keep `verify.py` outside `workspace/`. It may read the original
   workspace through `Path(__file__).parent / "workspace"` to check that files the agent was
   told not to touch are unchanged.
5. **Cross-platform.** Must pass on Linux, macOS and Windows: normalize `\r\n`, use
   `sys.executable` instead of `python`, no shell scripts.
6. **Small.** A capable agent should finish in a few minutes. Set `timeout` accordingly.
7. **One clear win condition.** The prompt should state what success means. Hidden checks may
   enforce things a careful engineer would infer (e.g. "do not modify the test file", the
   repo's AGENTS.md), but must not test unstated preferences.
8. **Verify behavior, not wording.** Prefer running the code over grepping it. When structure
   matters (a refactor), check it with `ast`, not regexes over source text.
9. **Explain the trap.** If the task is designed to catch a failure mode (over-editing,
   ignoring instructions, weak tests), say so in the tags and add a test in
   `tests/test_tasks.py` showing a plausible wrong answer fails.

Changing an existing task's prompt, workspace or verifier changes what the benchmark
measures. Bump the task id (`my-task-v2`) instead of editing it in place once results have been
published.

## Adapter rules

- Keep `build_command` and `parse_output` pure and unit-test them against captured CLI
  output in `tests/test_adapters.py`. CI never calls a real agent.
- Report `None` for anything the CLI does not report. Never estimate cost silently; if you
  add pricing, make it opt-in through `--agent-opt`.
- Do not let a parse failure lose the run: `Adapter._safe_parse` already wraps
  `parse_output`.

## Pull requests

- One task or one adapter per PR.
- Add a CHANGELOG entry under `Unreleased`.
- `uv run pytest` and `uv run ruff check .` must pass.
