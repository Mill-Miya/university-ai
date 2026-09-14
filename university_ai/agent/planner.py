from __future__ import annotations

from typing import Protocol

from university_ai.agent.models import AgentRequest, ToolCall


class Planner(Protocol):
    """Future complex-task boundary. Phase 1 never invokes a planner automatically."""

    def plan(self, request: AgentRequest, context: object) -> list[ToolCall]: ...
