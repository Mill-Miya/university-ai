from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from university_ai.agent.models import PolicyDecision, ToolCall, ToolResult


class ToolValidationError(ValueError):
    pass


class ToolDeniedError(PermissionError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    required_arguments: frozenset[str]
    execute: Callable[[dict], ToolResult]


class ToolRegistry:
    def __init__(self, policy_engine) -> None:
        self._policy = policy_engine
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def execute(self, call: ToolCall) -> tuple[ToolResult, PolicyDecision]:
        tool = self._tools.get(call.name)
        if tool is None:
            raise ToolValidationError("tool does not exist")
        decision = self._policy.evaluate(call)
        if not self._policy.permits(decision):
            raise ToolDeniedError(f"tool is not permitted: {decision}")
        missing = tool.required_arguments - call.arguments.keys()
        if missing:
            raise ToolValidationError(f"missing tool arguments: {', '.join(sorted(missing))}")
        return tool.execute(call.arguments), decision
