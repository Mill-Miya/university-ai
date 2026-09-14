from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Intent(StrEnum):
    CHAT = "CHAT"
    QUESTION = "QUESTION"
    TASK_QUERY = "TASK_QUERY"
    EXAM_QUERY = "EXAM_QUERY"
    COURSE_QUERY = "COURSE_QUERY"
    SCHEDULE_QUERY = "SCHEDULE_QUERY"
    DOCUMENT_SEARCH = "DOCUMENT_SEARCH"
    SCREEN_EXPLAIN = "SCREEN_EXPLAIN"
    SCREEN_TRANSLATE = "SCREEN_TRANSLATE"
    SCREEN_SUMMARIZE = "SCREEN_SUMMARIZE"
    BACKGROUND_EVENT = "BACKGROUND_EVENT"
    NOTIFICATION_EVENT = "NOTIFICATION_EVENT"


class PolicyDecision(StrEnum):
    READ_ONLY = "READ_ONLY"
    SAFE_ACTION = "SAFE_ACTION"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    DENIED = "DENIED"


class ModelRoute(StrEnum):
    RULE_ONLY = "RULE_ONLY"
    FAST = "FAST"
    FAST_VISION = "FAST_VISION"
    DEEP = "DEEP"


@dataclass(frozen=True)
class AgentRequest:
    text: str
    now: datetime
    explicit_intent: Intent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResponse:
    text: str
    intent: Intent
    route: ModelRoute
    policy: PolicyDecision
    tool_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
