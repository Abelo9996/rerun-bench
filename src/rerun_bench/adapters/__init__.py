"""Agent adapters. Add one by subclassing ``Adapter`` and registering it in ``ADAPTERS``."""

from __future__ import annotations

from .base import Adapter, AgentResult, Usage
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .mock import MockAdapter
from .opencode import OpencodeAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
    "opencode": OpencodeAdapter,
    "mock": MockAdapter,
}

REAL_AGENTS = frozenset({"claude", "codex", "opencode"})


def get_adapter(
    name: str, model: str | None = None, options: dict[str, str] | None = None
) -> Adapter:
    try:
        cls = ADAPTERS[name]
    except KeyError:
        raise ValueError(f"unknown agent {name!r}; choose from {sorted(ADAPTERS)}") from None
    return cls(model=model, options=options)


__all__ = ["ADAPTERS", "REAL_AGENTS", "Adapter", "AgentResult", "Usage", "get_adapter"]
