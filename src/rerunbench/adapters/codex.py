"""OpenAI Codex CLI: ``codex exec --json`` (JSONL event stream).

Token usage arrives on ``turn.completed`` events as ``usage.{input_tokens,
cached_input_tokens, output_tokens}``; it is summed across turns. Codex does not report a
dollar cost, so ``cost_usd`` stays ``None`` unless a price is supplied with
``--agent-opt usd_per_mtok_in=...`` and ``usd_per_mtok_out=...``.
"""

from __future__ import annotations

from pathlib import Path

from .base import Adapter, Usage, as_float, as_int, iter_json_lines


class CodexAdapter(Adapter):
    name = "codex"
    binary = "codex"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        sandbox = self.options.get("sandbox", "workspace-write")
        cmd = [self.binary, "exec", "--json", "--skip-git-repo-check", "--ephemeral",
               "--sandbox", sandbox, "--cd", str(workspace)]
        if self.model:
            cmd += ["--model", self.model]
        cmd.append(prompt)
        return cmd

    def parse_output(self, stdout: str, stderr: str) -> Usage:
        inp = cached = out = 0
        seen = False
        turns = 0
        model = None
        is_error = None
        for ev in iter_json_lines(stdout):
            etype = ev.get("type", "")
            if etype == "turn.completed":
                turns += 1
                u = ev.get("usage") or {}
                seen = True
                inp += as_int(u.get("input_tokens")) or 0
                cached += as_int(u.get("cached_input_tokens")) or 0
                out += as_int(u.get("output_tokens")) or 0
            elif etype in ("turn.failed", "error"):
                is_error = True
            if not model and isinstance(ev.get("model"), str):
                model = ev["model"]
        if not seen:
            return Usage(model=model or self.model, is_error=is_error)
        # Codex reports cached tokens as a subset of input tokens; split them out.
        uncached = max(inp - cached, 0)
        cost = None
        p_in = as_float(_num(self.options.get("usd_per_mtok_in")))
        p_out = as_float(_num(self.options.get("usd_per_mtok_out")))
        if p_in is not None and p_out is not None:
            p_cache = as_float(_num(self.options.get("usd_per_mtok_cached"))) or p_in
            cost = (uncached * p_in + cached * p_cache + out * p_out) / 1e6
        return Usage(
            input_tokens=uncached,
            output_tokens=out,
            cache_read_tokens=cached,
            cost_usd=cost,
            model=model or self.model,
            num_turns=turns,
            is_error=is_error if is_error is not None else False,
        )


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
