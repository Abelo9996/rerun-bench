"""Adapter protocol: how rerunbench drives one coding-agent CLI headlessly."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Usage:
    """What the CLI reported about one run. ``None`` means "not reported", never zero."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    cost_usd: float | None = None
    model: str | None = None
    num_turns: int | None = None
    is_error: bool | None = None

    @property
    def total_tokens(self) -> int | None:
        parts = [self.input_tokens, self.output_tokens, self.cache_read_tokens,
                 self.cache_write_tokens]
        if all(p is None for p in parts):
            return None
        return sum(p or 0 for p in parts)


@dataclass
class AgentResult:
    exit_code: int | None
    wall_time_s: float
    timed_out: bool
    usage: Usage
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None
    extra: dict = field(default_factory=dict)


class Adapter(ABC):
    """Subclasses implement command construction and output parsing; ``run`` is shared.

    Keep ``build_command`` and ``parse_output`` pure so they can be unit-tested against
    synthetic CLI output without spending any model quota.
    """

    name: str = ""
    binary: str = ""

    def __init__(self, model: str | None = None, options: dict[str, str] | None = None):
        self.model = model
        self.options = dict(options or {})

    # ---- pure, unit-testable parts -------------------------------------------------
    @abstractmethod
    def build_command(self, prompt: str, workspace: Path) -> list[str]: ...

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str) -> Usage: ...

    # ---- environment probing -------------------------------------------------------
    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def version(self) -> str | None:
        exe = shutil.which(self.binary)
        if exe is None:
            return None
        try:
            proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        out = (proc.stdout or proc.stderr).strip().splitlines()
        return out[0].strip() if out else None

    # ---- execution -------------------------------------------------------------------
    def run(self, prompt: str, workspace: Path, timeout: int, seed: int, run_key: str) -> AgentResult:
        """Run the agent once inside ``workspace``. ``seed``/``run_key`` are for the mock."""
        cmd = self.build_command(prompt, workspace)
        exe = shutil.which(cmd[0])
        if exe is None:
            return AgentResult(None, 0.0, False, Usage(), error=f"{cmd[0]!r} not found on PATH")
        cmd = [exe, *cmd[1:]]
        env = {**os.environ, **self.extra_env()}
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd, cwd=workspace, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, env=env, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            wall = time.perf_counter() - start
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (
                exc.stdout or "")
            return AgentResult(None, wall, True, self._safe_parse(stdout, ""),
                               stdout_tail=stdout[-2000:], error="timeout")
        wall = time.perf_counter() - start
        return AgentResult(
            exit_code=proc.returncode,
            wall_time_s=wall,
            timed_out=False,
            usage=self._safe_parse(proc.stdout, proc.stderr),
            stdout_tail=proc.stdout[-2000:],
            stderr_tail=proc.stderr[-2000:],
        )

    def extra_env(self) -> dict[str, str]:
        return {}

    def _safe_parse(self, stdout: str, stderr: str) -> Usage:
        try:
            return self.parse_output(stdout, stderr)
        except Exception:  # a parse failure must never lose the run record
            return Usage()


def iter_json_lines(text: str):
    """Yield every JSON object found one-per-line in ``text``; skip anything else."""
    import json

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def as_int(v) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        return int(v)
    return None


def as_float(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    return None
