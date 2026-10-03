"""Claude Code: ``claude -p <prompt> --output-format json``.

The JSON result object carries ``total_cost_usd``, ``usage`` (input/output/cache tokens),
``num_turns``, ``is_error`` and a ``modelUsage`` map keyed by model id.

Isolation: by default the run loads only project and local settings (the task workspace has
none) and ignores MCP servers outside ``--mcp-config``, so the benchmarker's personal hooks,
plugins and MCP servers do not leak into the measurement. ``--agent-opt isolate=0`` turns
this off; ``--agent-opt bare=1`` adds ``--bare`` (requires ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import Adapter, Usage, as_float, as_int, iter_json_lines


class ClaudeAdapter(Adapter):
    name = "claude"
    binary = "claude"

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
        model = None
        model_usage = obj.get("modelUsage") or {}
        if isinstance(model_usage, dict) and model_usage:
            # The model that produced the most output tokens is the "main" model.
            model = max(model_usage, key=lambda k: (model_usage[k] or {}).get("outputTokens", 0))
        return Usage(
            input_tokens=as_int(usage.get("input_tokens")),
            output_tokens=as_int(usage.get("output_tokens")),
            cache_read_tokens=as_int(usage.get("cache_read_input_tokens")),
            cache_write_tokens=as_int(usage.get("cache_creation_input_tokens")),
            cost_usd=as_float(obj.get("total_cost_usd", obj.get("cost_usd"))),
            model=model or obj.get("model"),
            num_turns=as_int(obj.get("num_turns")),
            is_error=obj.get("is_error") if isinstance(obj.get("is_error"), bool) else None,
        )
