from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from university_ai.agent.models import ModelRoute
from university_ai.llm.models import ImageInput


class OcrQuality(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"
    UNUSABLE = "UNUSABLE"


@dataclass(frozen=True)
class PerceptionDecision:
    route: ModelRoute
    quality: OcrQuality
    reason: str


@dataclass(frozen=True)
class PerceptionInput:
    image: ImageInput
    ocr_text: str = ""
    requires_visual_reasoning: bool = False
