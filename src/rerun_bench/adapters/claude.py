"""Claude Code: ``claude -p <prompt> --output-format json``.

The JSON result object carries ``total_cost_usd``, ``usage`` (input/output/cache tokens of
the main conversation), ``num_turns``, ``is_error`` and a ``modelUsage`` map keyed by model
id with ``inputTokens``, ``outputTokens``, ``cacheReadInputTokens``,
``cacheCreationInputTokens`` and ``costUSD`` for every model the session called, including
subagents and background calls. Tokens are summed over ``modelUsage`` so they cover the same
calls as ``total_cost_usd``; ``usage`` fills any field ``modelUsage`` does not carry.

Nested runs: when rerun-bench itself runs inside a Claude Code session, that session's
environment variables (``CLAUDECODE``, ``CLAUDE_CODE_SESSION_ID``, ``CLAUDE_EFFORT`` and
similar) are removed from the child's environment so the measured session starts like one
launched from a plain terminal. ``--agent-opt effort=<level>`` passes ``--effort``.

Isolation: by default the run loads only project and local settings (the task workspace has
none) and ignores MCP servers outside ``--mcp-config``, so the benchmarker's personal hooks,
plugins and MCP servers do not leak into the measurement. ``--agent-opt isolate=0`` turns
this off; ``--agent-opt bare=1`` adds ``--bare`` (requires ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import Adapter, Usage, as_float, as_int, iter_json_lines

# Set by a running Claude Code session for its own child processes. Inheriting them would
# make the measured session behave as a subprocess of the benchmarker's session.
NESTED_SESSION_ENV = frozenset(
    {
        "CLAUDECODE",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_SESSION_ATTENDED",
        "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_CODE_EXECPATH",
        "CLAUDE_CODE_SSE_PORT",
        "CLAUDE_PID",
        "CLAUDE_EFFORT",
    }
)


class ClaudeAdapter(Adapter):
    name = "claude"
    binary = "claude"

    def unset_env(self) -> frozenset[str]:
        return NESTED_SESSION_ENV

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        mode = self.options.get("permission_mode", "bypassPermissions")
        cmd = [
            self.binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            mode,
            "--no-session-persistence",
        ]
        if self.options.get("isolate", "1") not in ("0", "false", "no"):
            cmd += ["--setting-sources", "project,local", "--strict-mcp-config"]
        if self.options.get("bare", "0") in ("1", "true", "yes"):
            cmd.append("--bare")
        if self.model:
            cmd += ["--model", self.model]
        if self.options.get("effort"):
            cmd += ["--effort", self.options["effort"]]
        if "max_turns" in self.options:
            cmd += ["--max-turns", str(self.options["max_turns"])]
        return cmd

    def parse_output(self, stdout: str, stderr: str) -> Usage:
        obj = None
        text = stdout.strip()
        if text.startswith("{"):
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                obj = None
        if obj is None:  # tolerate banners or stream-json: take the last result object
            for cand in iter_json_lines(stdout):
                if cand.get("type") == "result" or "total_cost_usd" in cand:
                    obj = cand
        if not isinstance(obj, dict):
            return Usage()
        usage = obj.get("usage") or {}
        tokens = {
            "input": as_int(usage.get("input_tokens")),
            "output": as_int(usage.get("output_tokens")),
            "cache_read": as_int(usage.get("cache_read_input_tokens")),
            "cache_write": as_int(usage.get("cache_creation_input_tokens")),
        }
        model = None
        model_usage = obj.get("modelUsage")
        if isinstance(model_usage, dict) and model_usage:
            per_model = {k: v for k, v in model_usage.items() if isinstance(v, dict)}
            if per_model:
                summed = _sum_model_usage(per_model.values())
                tokens = {k: v if v is not None else tokens[k] for k, v in summed.items()}
                # The model that produced the most output tokens is the "main" model.
                model = max(per_model, key=lambda k: as_int(per_model[k].get("outputTokens")) or 0)
        return Usage(
            input_tokens=tokens["input"],
            output_tokens=tokens["output"],
            cache_read_tokens=tokens["cache_read"],
            cache_write_tokens=tokens["cache_write"],
            cost_usd=as_float(obj.get("total_cost_usd", obj.get("cost_usd"))),
            model=model or obj.get("model"),
            num_turns=as_int(obj.get("num_turns")),
            is_error=obj.get("is_error") if isinstance(obj.get("is_error"), bool) else None,
        )


_MODEL_USAGE_KEYS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_read": "cacheReadInputTokens",
    "cache_write": "cacheCreationInputTokens",
}


def _sum_model_usage(entries) -> dict[str, int | None]:
    out: dict[str, int | None] = dict.fromkeys(_MODEL_USAGE_KEYS)
    for entry in entries:
        for field, key in _MODEL_USAGE_KEYS.items():
            v = as_int(entry.get(key))
            if v is not None:
                out[field] = (out[field] or 0) + v
    return out
