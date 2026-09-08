from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True)
class LlmRequest:
    prompt: str
    system_prompt: str | None = None
    context: str | None = None
    temperature: float = 0.3
    max_tokens: int = 512

@dataclass(frozen=True)
class LlmResponse:
    text: str
    model: str
    runtime: str
    created_at: datetime
    duration_seconds: float
    metadata: dict[str, object] = field(default_factory=dict)
