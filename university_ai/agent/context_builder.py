from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    university: object


class ContextBuilder:
    """Small adapter around the existing deterministic ContextEngine."""

    def __init__(self, context_engine) -> None:
        self._context_engine = context_engine

    def build(self, request) -> AgentContext:
        return AgentContext(self._context_engine.build(request.now))
