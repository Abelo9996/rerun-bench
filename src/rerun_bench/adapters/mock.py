"""Deterministic mock agent for tests, demos and CI. Spends no tokens, needs no API key.

Behaviour per run is a pure function of ``(seed, run_key, options)``:

- with probability ``pass_prob`` it overlays the task's reference ``solution/`` (so the real
  verifier passes); otherwise it leaves the workspace untouched or makes a wrong edit;
- token counts are drawn from a lognormal with mean ``tokens`` and coefficient of
  variation ``token_cv``; cost is ``tokens * usd_per_mtok / 1e6``;
- wall time is simulated (``wall_s`` mean, ``wall_cv``) rather than slept, so a 50-run
  demo finishes in seconds.

Options (``--agent-opt key=value``): pass_prob, tokens, token_cv, usd_per_mtok,
wall_s, wall_cv, wrong_edit_prob. Per-task pass probabilities can be given as
``pass_prob.<task-id>=0.2``.
"""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

from .. import workspace as ws
from .base import Adapter, AgentResult, Usage

DEFAULTS = {
    "pass_prob": 0.8,
    "tokens": 20000.0,
    "token_cv": 0.35,
    "usd_per_mtok": 3.0,
    "wall_s": 45.0,
    "wall_cv": 0.4,
    "wrong_edit_prob": 0.5,
}


def _lognormal(rng: random.Random, mean: float, cv: float) -> float:
    if mean <= 0:
        return 0.0
    if cv <= 0:
        return mean
    sigma2 = math.log1p(cv * cv)
    mu = math.log(mean) - sigma2 / 2
    return rng.lognormvariate(mu, math.sqrt(sigma2))


class MockAdapter(Adapter):
    name = "mock"
    binary = ""

    def __init__(self, model: str | None = None, options: dict[str, str] | None = None):
        super().__init__(model or "mock-1", options)
        self.solution_dir: Path | None = None  # set by the runner per task

    def _opt(self, key: str, task_id: str | None = None) -> float:
        if task_id and f"{key}.{task_id}" in self.options:
            return float(self.options[f"{key}.{task_id}"])
        return float(self.options.get(key, DEFAULTS[key]))

    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        from .. import __version__

        return f"mock {__version__}"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["mock", prompt]

    def parse_output(self, stdout: str, stderr: str) -> Usage:
        return Usage()

    def run(
        self, prompt: str, workspace: Path, timeout: int, seed: int, run_key: str
    ) -> AgentResult:
        task_id = run_key.split("/", 1)[0]
        digest = hashlib.sha256(f"{seed}|{self.model}|{run_key}".encode()).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        success = rng.random() < self._opt("pass_prob", task_id)
        wrong_edit = (not success) and rng.random() < self._opt("wrong_edit_prob")
        if success and self.solution_dir is not None and self.solution_dir.is_dir():
            ws.overlay(self.solution_dir, workspace)
        elif wrong_edit:
            (workspace / "MOCK_NOTES.md").write_text(
                "The mock agent edited the wrong file on this run.\n", encoding="utf-8"
            )
        total = _lognormal(rng, self._opt("tokens"), self._opt("token_cv"))
        out_share = 0.08 + 0.04 * rng.random()
        out_tok = int(total * out_share)
        cache_tok = int(total * 0.6)
        in_tok = max(int(total) - out_tok - cache_tok, 0)
        cost = (in_tok + out_tok + cache_tok) * self._opt("usd_per_mtok") / 1e6
        wall = _lognormal(rng, self._opt("wall_s"), self._opt("wall_cv"))
        return AgentResult(
            exit_code=0,
            wall_time_s=round(wall, 3),
            timed_out=False,
            usage=Usage(
                input_tokens=in_tok,
                output_tokens=out_tok,
                cache_read_tokens=cache_tok,
                cache_write_tokens=0,
                cost_usd=round(cost, 6),
                model=self.model,
                num_turns=1 + int(rng.random() * 6),
                is_error=False,
            ),
            extra={"simulated_wall_time": True},
        )
