"""opencode: ``opencode run --format json <prompt>`` (JSONL event stream).

``step_finish`` events carry ``part.tokens.{input,output,reasoning,cache.{read,write}}`` and
``part.cost``; both are summed across steps. Field names follow opencode's session schema;
the parser ignores anything it does not recognise rather than failing the run.
"""

from __future__ import annotations

from pathlib import Path

from .base import Adapter, Usage, as_float, as_int, iter_json_lines


class OpencodeAdapter(Adapter):
    name = "opencode"
    binary = "opencode"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        cmd = [self.binary, "run", "--format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        cmd.append(prompt)
        return cmd

    def parse_output(self, stdout: str, stderr: str) -> Usage:
        inp = out = cr = cw = 0
        cost = 0.0
        seen_tokens = seen_cost = False
        steps = 0
        model = None
        is_error = None
        for ev in iter_json_lines(stdout):
            etype = ev.get("type")
            part = ev.get("part") if isinstance(ev.get("part"), dict) else ev
            if etype == "error":
                is_error = True
            if etype != "step_finish" and part.get("type") != "step-finish":
                if not model:
                    model = _model_of(part) or _model_of(ev)
                continue
            steps += 1
            tok = part.get("tokens") or {}
            if tok:
                seen_tokens = True
                inp += as_int(tok.get("input")) or 0
                out += (as_int(tok.get("output")) or 0) + (as_int(tok.get("reasoning")) or 0)
                cache = tok.get("cache") or {}
                cr += as_int(cache.get("read")) or 0
                cw += as_int(cache.get("write")) or 0
            c = as_float(part.get("cost"))
            if c is not None:
                seen_cost = True
                cost += c
            model = model or _model_of(part)
        return Usage(
            input_tokens=inp if seen_tokens else None,
            output_tokens=out if seen_tokens else None,
            cache_read_tokens=cr if seen_tokens else None,
            cache_write_tokens=cw if seen_tokens else None,
            cost_usd=cost if seen_cost else None,
            model=model or self.model,
            num_turns=steps or None,
            is_error=is_error,
        )


def _model_of(d: dict) -> str | None:
    for key in ("modelID", "model"):
        v = d.get(key)
        if isinstance(v, str) and v:
            prov = d.get("providerID")
            return f"{prov}/{v}" if isinstance(prov, str) and prov and "/" not in v else v
    return None
