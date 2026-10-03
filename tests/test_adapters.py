"""Real adapters are tested only on command construction and parsing of synthetic output.

Nothing here invokes a real agent CLI or spends model quota.
"""

import json
from pathlib import Path

import pytest

from rerunbench.adapters import ADAPTERS, get_adapter
from rerunbench.adapters.base import Usage

WS = Path("/tmp/ws")

CLAUDE_JSON = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 41234,
        "num_turns": 7,
        "result": "Fixed the median bug.",
        "session_id": "abc",
        "total_cost_usd": 0.0831,
        "usage": {
            "input_tokens": 1200,
            "cache_creation_input_tokens": 9000,
            "cache_read_input_tokens": 45000,
            "output_tokens": 1800,
        },
        "modelUsage": {
            "claude-haiku-4-5": {"inputTokens": 300, "outputTokens": 40},
            "claude-sonnet-4-5": {"inputTokens": 900, "outputTokens": 1760},
        },
    }
)

CODEX_JSONL = (
    "\n".join(
        json.dumps(e)
        for e in [
            {"type": "thread.started", "thread_id": "t1"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": "ok"}},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 24000,
                    "cached_input_tokens": 20000,
                    "output_tokens": 900,
                },
            },
            {"type": "turn.started"},
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 100},
            },
        ]
    )
    + "\n"
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


def test_claude_parse():
    u = get_adapter("claude").parse_output(CLAUDE_JSON, "")
    assert u.input_tokens == 1200 and u.output_tokens == 1800
    assert u.cache_read_tokens == 45000 and u.cache_write_tokens == 9000
    assert u.total_tokens == 1200 + 1800 + 45000 + 9000
    assert u.cost_usd == pytest.approx(0.0831)
    assert u.model == "claude-sonnet-4-5"
    assert u.num_turns == 7 and u.is_error is False


def test_claude_parse_tolerates_noise_and_garbage():
    noisy = "some banner\n" + CLAUDE_JSON + "\n"
    assert get_adapter("claude").parse_output(noisy, "").cost_usd == pytest.approx(0.0831)
    assert get_adapter("claude").parse_output("not json", "") == Usage()
    assert get_adapter("claude")._safe_parse("{bad", "") == Usage()


def test_codex_command():
    cmd = get_adapter("codex", "gpt-5-codex").build_command("fix it", WS)
    assert cmd[:3] == ["codex", "exec", "--json"]
    assert "--skip-git-repo-check" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
    assert cmd[cmd.index("--cd") + 1] == str(WS)
    assert cmd[cmd.index("--model") + 1] == "gpt-5-codex"
    assert cmd[-1] == "fix it"


def test_codex_parse():
    u = get_adapter("codex", "gpt-5-codex").parse_output(CODEX_JSONL, "")
    assert u.input_tokens == 25000 - 20000
    assert u.cache_read_tokens == 20000
    assert u.output_tokens == 1000
    assert u.num_turns == 2
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
    assert u2.cost_usd == pytest.approx((5000 * 1.25 + 20000 * 0.125 + 1000 * 10) / 1e6)
    assert get_adapter("codex").parse_output("", "").total_tokens is None


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
    from rerunbench import tasks as tasks_mod
    from rerunbench import workspace as ws

    t = next(x for x in all_tasks if x.id == "edit-config")
    a = get_adapter("mock", options={"pass_prob": "1", f"pass_prob.{t.id}": "0"})
    a.solution_dir = t.solution
    work = ws.fresh_copy(t.workspace)
    try:
        a.run(t.prompt, work, 10, seed=0, run_key=f"{t.id}/0")
        assert not tasks_mod.verify(t, work).passed
    finally:
        ws.cleanup(work)
