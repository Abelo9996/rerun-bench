"""Real adapters are tested only on command construction and parsing of synthetic output.

Nothing here invokes a real agent CLI or spends model quota.
"""

import json
from pathlib import Path

import pytest

from rerun_bench.adapters import ADAPTERS, get_adapter
from rerun_bench.adapters.base import Usage

WS = Path("/tmp/ws")

# Shape of `claude -p --output-format json` from Claude Code 2.1.x. Values are synthetic;
# the field names and nesting follow the real output. Top-level `usage` covers the main
# conversation only; `modelUsage` covers every model the session called, and the adapter
# sums it so tokens line up with `total_cost_usd`.
CLAUDE_JSON = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "api_error_status": None,
        "duration_ms": 41234,
        "duration_api_ms": 39001,
        "num_turns": 7,
        "result": "Fixed the median bug.",
        "stop_reason": "end_turn",
        "session_id": "00000000-0000-0000-0000-000000000000",
        "total_cost_usd": 0.0831,
        "usage": {
            "input_tokens": 900,
            "cache_creation_input_tokens": 9000,
            "cache_read_input_tokens": 45000,
            "output_tokens": 1760,
            "output_tokens_details": {"thinking_tokens": 120},
            "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
            "service_tier": "standard",
            "cache_creation": {"ephemeral_1h_input_tokens": 9000, "ephemeral_5m_input_tokens": 0},
            "iterations": [],
        },
        "modelUsage": {
            "claude-haiku-4-5": {
                "inputTokens": 300,
                "outputTokens": 40,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 500,
                "webSearchRequests": 0,
                "costUSD": 0.001,
                "contextWindow": 200000,
                "maxOutputTokens": 64000,
            },
            "claude-sonnet-4-5": {
                "inputTokens": 900,
                "outputTokens": 1760,
                "cacheReadInputTokens": 45000,
                "cacheCreationInputTokens": 9000,
                "webSearchRequests": 0,
                "costUSD": 0.0821,
                "contextWindow": 200000,
                "maxOutputTokens": 64000,
                "thinkingTokens": 120,
            },
        },
        "permission_denials": [],
        "terminal_reason": "completed",
        "uuid": "00000000-0000-0000-0000-000000000001",
    }
)

# Shape of `codex exec --json` from Codex CLI 0.160. Transient `error` events (retries) can
# precede a successful turn; `cached_input_tokens` and `cache_write_input_tokens` are subsets
# of `input_tokens`, and `reasoning_output_tokens` is a subset of `output_tokens`.
CODEX_JSONL = (
    "\n".join(
        json.dumps(e)
        for e in [
            {"type": "thread.started", "thread_id": "00000000-0000-0000-0000-000000000000"},
            {"type": "turn.started"},
            {"type": "error", "message": "Reconnecting... 2/5 (stream disconnected)"},
            {
                "type": "item.started",
                "item": {
                    "id": "item_0",
                    "type": "command_execution",
                    "command": "/bin/zsh -lc 'cat stats.py'",
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "command_execution",
                    "command": "/bin/zsh -lc 'cat stats.py'",
                    "aggregated_output": "def median(xs): ...",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "ok"},
            },
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 24000,
                    "cached_input_tokens": 18000,
                    "cache_write_input_tokens": 2000,
                    "output_tokens": 900,
                    "reasoning_output_tokens": 300,
                },
            },
            {"type": "turn.started"},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 0,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 100,
                    "reasoning_output_tokens": 0,
                },
            },
        ]
    )
    + "\n"
)

# A run whose model is unavailable: retries, then `turn.failed`, and no usage.
CODEX_FAILED_JSONL = "\n".join(
    json.dumps(e)
    for e in [
        {"type": "thread.started", "thread_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "turn.started"},
        {"type": "error", "message": "Reconnecting... 1/5 (unexpected status 404 Not Found)"},
        {"type": "error", "message": "unexpected status 404 Not Found"},
        {"type": "turn.failed", "error": {"message": "unexpected status 404 Not Found"}},
    ]
)

OPENCODE_JSONL = "\n".join(
    json.dumps(e)
    for e in [
        {"type": "step_start", "part": {"type": "step-start"}},
        {
            "type": "text",
            "part": {
                "type": "text",
                "text": "Working",
                "providerID": "anthropic",
                "modelID": "claude-sonnet-4-5",
            },
        },
        {
            "type": "step_finish",
            "part": {
                "type": "step-finish",
                "cost": 0.012,
                "tokens": {
                    "input": 500,
                    "output": 200,
                    "reasoning": 50,
                    "cache": {"read": 4000, "write": 100},
                },
            },
        },
        {
            "type": "step_finish",
            "part": {
                "type": "step-finish",
                "cost": 0.003,
                "tokens": {
                    "input": 100,
                    "output": 20,
                    "reasoning": 0,
                    "cache": {"read": 4500, "write": 0},
                },
            },
        },
    ]
)


def test_registry():
    assert set(ADAPTERS) == {"claude", "codex", "opencode", "mock"}
    with pytest.raises(ValueError):
        get_adapter("nope")


def test_claude_command():
    cmd = get_adapter("claude", "sonnet").build_command("do it", WS)
    assert cmd[:3] == ["claude", "-p", "do it"]
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert "--permission-mode" in cmd
    assert "--model" not in get_adapter("claude").build_command("x", WS)
    cmd = get_adapter(
        "claude", options={"max_turns": "20", "permission_mode": "acceptEdits"}
    ).build_command("x", WS)
    assert cmd[cmd.index("--max-turns") + 1] == "20"
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"


def test_claude_isolation_flags():
    cmd = get_adapter("claude").build_command("x", WS)
    assert cmd[cmd.index("--setting-sources") + 1] == "project,local"
    assert "--strict-mcp-config" in cmd and "--bare" not in cmd
    cmd = get_adapter("claude", options={"isolate": "0", "bare": "1"}).build_command("x", WS)
    assert "--setting-sources" not in cmd and "--bare" in cmd


def test_claude_parse():
    u = get_adapter("claude").parse_output(CLAUDE_JSON, "")
    # Summed over modelUsage (both models), not just the main conversation's `usage`.
    assert u.input_tokens == 1200 and u.output_tokens == 1800
    assert u.cache_read_tokens == 45000 and u.cache_write_tokens == 9500
    assert u.total_tokens == 1200 + 1800 + 45000 + 9500
    assert u.cost_usd == pytest.approx(0.0831)
    assert u.model == "claude-sonnet-4-5"
    assert u.num_turns == 7 and u.is_error is False


def test_claude_parse_without_model_usage_falls_back_to_usage():
    obj = json.loads(CLAUDE_JSON)
    del obj["modelUsage"]
    u = get_adapter("claude").parse_output(json.dumps(obj), "")
    assert u.input_tokens == 900 and u.output_tokens == 1760
    assert u.cache_read_tokens == 45000 and u.cache_write_tokens == 9000
    assert u.model is None


def test_claude_strips_nested_session_env():
    a = get_adapter("claude")
    parent = {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "ANTHROPIC_API_KEY": "k",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
        "CLAUDE_CODE_SESSION_ID": "s",
        "CLAUDE_CODE_CHILD_SESSION": "1",
        "CLAUDE_EFFORT": "high",
        "CLAUDE_CODE_USE_BEDROCK": "1",
    }
    env = a.child_env(parent)
    assert env["PATH"] == "/usr/bin" and env["ANTHROPIC_API_KEY"] == "k"
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1", "user configuration must pass through"
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_EFFORT"):
        assert k not in env
    cmd = get_adapter("claude", options={"effort": "low"}).build_command("x", WS)
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert "--effort" not in a.build_command("x", WS)


def test_bin_option_overrides_binary():
    a = get_adapter("codex", options={"bin": "/opt/codex-next/bin/codex"})
    assert a.binary == "/opt/codex-next/bin/codex"
    assert a.build_command("x", WS)[0] == "/opt/codex-next/bin/codex"
    assert get_adapter("codex").binary == "codex"


def test_claude_parse_tolerates_noise_and_garbage():
    noisy = "some banner\n" + CLAUDE_JSON + "\n"
    assert get_adapter("claude").parse_output(noisy, "").cost_usd == pytest.approx(0.0831)
    assert get_adapter("claude").parse_output("not json", "") == Usage()
    assert get_adapter("claude")._safe_parse("{bad", "") == Usage()


def test_codex_command():
    cmd = get_adapter("codex", "gpt-5-codex").build_command("fix it", WS)
    assert cmd[:3] == ["codex", "exec", "--json"]
    assert "--skip-git-repo-check" in cmd and "--ephemeral" in cmd
    assert "--ignore-user-config" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
    assert cmd[cmd.index("--cd") + 1] == str(WS)
    assert cmd[cmd.index("--model") + 1] == "gpt-5-codex"
    assert cmd[-1] == "fix it"
    cmd = get_adapter("codex", options={"isolate": "0", "effort": "high"}).build_command("x", WS)
    assert "--ignore-user-config" not in cmd and "--model" not in cmd
    assert cmd[cmd.index("-c") + 1] == "model_reasoning_effort=high"


def test_codex_parse():
    u = get_adapter("codex", "gpt-5-codex").parse_output(CODEX_JSONL, "")
    assert u.input_tokens == 25000 - 18000 - 2000
    assert u.cache_read_tokens == 18000 and u.cache_write_tokens == 2000
    assert u.output_tokens == 1000, "reasoning tokens are part of output_tokens"
    assert u.num_turns == 2
    assert u.is_error is False, "a retried transient error is not a failed run"
    assert u.cost_usd is None, "codex reports no cost; never invent one"
    assert u.model == "gpt-5-codex"
    priced = get_adapter(
        "codex",
        options={
            "usd_per_mtok_in": "1.25",
            "usd_per_mtok_out": "10",
            "usd_per_mtok_cached": "0.125",
        },
    )
    u2 = priced.parse_output(CODEX_JSONL, "")
    expected = (5000 * 1.25 + 18000 * 0.125 + 2000 * 1.25 + 1000 * 10) / 1e6
    assert u2.cost_usd == pytest.approx(expected)
    free_cache = get_adapter(
        "codex",
        options={"usd_per_mtok_in": "1", "usd_per_mtok_out": "1", "usd_per_mtok_cached": "0"},
    )
    assert free_cache.parse_output(CODEX_JSONL, "").cost_usd == pytest.approx(
        (5000 + 2000 + 1000) / 1e6
    ), "a cached price of 0 must not fall back to the input price"
    assert get_adapter("codex").parse_output("", "").total_tokens is None
    assert get_adapter("codex").parse_output(CODEX_JSONL, "").model is None


def test_codex_parse_failed_turn_and_old_schema():
    u = get_adapter("codex").parse_output(CODEX_FAILED_JSONL, "")
    assert u.is_error is True and u.total_tokens is None
    old = json.dumps(
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 5},
        }
    )
    u = get_adapter("codex").parse_output(old, "")
    assert u.input_tokens == 60 and u.cache_read_tokens == 40 and u.output_tokens == 5
    assert u.cache_write_tokens is None, "not reported by older CLIs, so not zero"


def test_opencode_command_and_parse():
    cmd = get_adapter("opencode", "anthropic/claude-sonnet-4-5").build_command("go", WS)
    assert cmd[:2] == ["opencode", "run"]
    assert cmd[cmd.index("--model") + 1] == "anthropic/claude-sonnet-4-5"
    assert cmd[-1] == "go"
    u = get_adapter("opencode").parse_output(OPENCODE_JSONL, "")
    assert u.input_tokens == 600 and u.output_tokens == 270
    assert u.cache_read_tokens == 8500 and u.cache_write_tokens == 100
    assert u.cost_usd == pytest.approx(0.015)
    assert u.num_turns == 2
    assert u.model == "anthropic/claude-sonnet-4-5"
    assert get_adapter("opencode").parse_output("plain text output", "").cost_usd is None


def test_missing_binary_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    a = get_adapter("codex")
    assert not a.available() and a.version() is None
    res = a.run("x", tmp_path, timeout=5, seed=0, run_key="t/0")
    assert res.exit_code is None and "not found" in res.error


def test_mock_is_deterministic(tmp_path):
    a = get_adapter("mock", options={"pass_prob": "0.5"})
    r1 = a.run("p", tmp_path, 10, seed=3, run_key="t/1")
    r2 = a.run("p", tmp_path, 10, seed=3, run_key="t/1")
    assert r1.usage == r2.usage and r1.wall_time_s == r2.wall_time_s
    r3 = a.run("p", tmp_path, 10, seed=4, run_key="t/1")
    assert r3.usage != r1.usage


def test_mock_per_task_pass_prob(tmp_path, all_tasks):
    from rerun_bench import tasks as tasks_mod
    from rerun_bench import workspace as ws

    t = next(x for x in all_tasks if x.id == "edit-config")
    a = get_adapter("mock", options={"pass_prob": "1", f"pass_prob.{t.id}": "0"})
    a.solution_dir = t.solution
    work = ws.fresh_copy(t.workspace)
    try:
        a.run(t.prompt, work, 10, seed=0, run_key=f"{t.id}/0")
        assert not tasks_mod.verify(t, work).passed
    finally:
        ws.cleanup(work)
