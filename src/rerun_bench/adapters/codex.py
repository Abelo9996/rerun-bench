"""OpenAI Codex CLI: ``codex exec --json`` (JSONL event stream).

Token usage arrives on ``turn.completed`` events as ``usage.{input_tokens,
cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens}``;
it is summed across turns. Cached and cache-write tokens are subsets of ``input_tokens`` and
reasoning tokens are a subset of ``output_tokens``, so they are split out or ignored rather
than added. Codex does not report a dollar cost, so ``cost_usd`` stays ``None`` unless a
price is supplied with ``--agent-opt usd_per_mtok_in=...`` and ``usd_per_mtok_out=...``.

``codex exec --json`` does not report which model it used. The recorded model is the one
passed with ``--model``; without it the model is ``None`` ("default" in reports).

Errors: Codex emits ``error`` events for transient problems it retries (``Reconnecting...
2/5``). A run counts as an error only on ``turn.failed``, or when error events appear and
no turn completes.

Isolation: by default the run passes ``--ignore-user-config`` so the benchmarker's
``config.toml`` (model, reasoning effort, plugins, notify hooks, MCP servers) does not leak
into the measurement; authentication still comes from ``CODEX_HOME``. ``--agent-opt
isolate=0`` turns this off. ``--agent-opt effort=<level>`` sets ``model_reasoning_effort``.
"""

from __future__ import annotations

from pathlib import Path

from .base import Adapter, Usage, as_float, as_int, iter_json_lines


class CodexAdapter(Adapter):
    name = "codex"
    binary = "codex"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        sandbox = self.options.get("sandbox", "workspace-write")
        cmd = [
            self.binary,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            sandbox,
            "--cd",
            str(workspace),
        ]
        if self.options.get("isolate", "1") not in ("0", "false", "no"):
            cmd.append("--ignore-user-config")
        if self.options.get("effort"):
            cmd += ["-c", f"model_reasoning_effort={self.options['effort']}"]
        if self.model:
            cmd += ["--model", self.model]
        cmd.append(prompt)
        return cmd

    def parse_output(self, stdout: str, stderr: str) -> Usage:
        inp = cached = cache_write = out = 0
        seen = seen_write = False
        turns = 0
        model = None
        failed = False
        error_events = 0
        for ev in iter_json_lines(stdout):
            etype = ev.get("type", "")
            if etype == "turn.completed":
                turns += 1
                u = ev.get("usage") or {}
                seen = True
                inp += as_int(u.get("input_tokens")) or 0
                cached += as_int(u.get("cached_input_tokens")) or 0
                if as_int(u.get("cache_write_input_tokens")) is not None:
                    seen_write = True
                    cache_write += as_int(u.get("cache_write_input_tokens"))
                out += as_int(u.get("output_tokens")) or 0
            elif etype == "turn.failed":
                failed = True
            elif etype == "error":
                error_events += 1
            if not model and isinstance(ev.get("model"), str):
                model = ev["model"]
        is_error = failed or (error_events > 0 and turns == 0)
        if not seen:
            return Usage(model=model or self.model, is_error=True if is_error else None)
        uncached = max(inp - cached - cache_write, 0)
        cost = None
        p_in = as_float(_num(self.options.get("usd_per_mtok_in")))
        p_out = as_float(_num(self.options.get("usd_per_mtok_out")))
        if p_in is not None and p_out is not None:
            p_cache = as_float(_num(self.options.get("usd_per_mtok_cached")))
            p_cache = p_in if p_cache is None else p_cache
            p_write = as_float(_num(self.options.get("usd_per_mtok_cache_write")))
            p_write = p_in if p_write is None else p_write
            cost = (uncached * p_in + cached * p_cache + cache_write * p_write + out * p_out) / 1e6
        return Usage(
            input_tokens=uncached,
            output_tokens=out,
            cache_read_tokens=cached,
            cache_write_tokens=cache_write if seen_write else None,
            cost_usd=cost,
            model=model or self.model,
            num_turns=turns,
            is_error=is_error,
        )


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
