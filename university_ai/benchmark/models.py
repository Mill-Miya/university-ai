from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class EvaluationType(StrEnum):
    CONTAINS = "contains"
    JAPANESE = "japanese"
    NO_THINKING = "no_thinking"
    JSON = "json"
    INTENT = "intent"
    TOOL = "tool"
    MANUAL = "manual"


class BenchmarkStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    category: str
    input: str
    expected: dict[str, Any]
    evaluation_type: EvaluationType
    timeout_seconds: float
    target: str = "llm"


@dataclass(frozen=True)
class BenchmarkResult:
    case_id: str
    category: str
    status: BenchmarkStatus
    output: str = ""
    reason: str | None = None
    total_latency_seconds: float | None = None
    ttft_seconds: float | None = None
    generation_seconds: float | None = None
    tokens_per_second: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    runtime: str | None = None
    memory_usage_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
