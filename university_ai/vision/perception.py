from __future__ import annotations

import re

from university_ai.agent.models import Intent, ModelRoute
from university_ai.vision.models import OcrQuality, PerceptionDecision


class OcrQualityAnalyzer:
    """Conservative local heuristic; it never treats OCR text as instructions."""

    def __init__(self, minimum_characters: int = 12) -> None:
        self._minimum = minimum_characters

    def assess(self, text: str | None) -> OcrQuality:
        value = (text or "").strip()
        if not value:
            return OcrQuality.UNUSABLE
        meaningful = len(re.findall(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff]", value))
        if len(value) >= self._minimum and meaningful / max(len(value), 1) >= 0.45:
            return OcrQuality.HIGH
        return OcrQuality.LOW


class PerceptionRouter:
    """Chooses text or vision without knowing a backend/model name."""

    def __init__(self, model_router, analyzer: OcrQualityAnalyzer | None = None) -> None:
        self._model_router = model_router
        self._analyzer = analyzer or OcrQualityAnalyzer()

    def decide(self, intent: Intent, ocr_text: str | None, *, requires_visual_reasoning: bool,
               vision_available: bool) -> PerceptionDecision:
        quality = self._analyzer.assess(ocr_text)
        route = self._model_router.route(
            intent, ocr_quality=quality, requires_visual_reasoning=requires_visual_reasoning,
            vision_available=vision_available,
        )
        if route is ModelRoute.FAST_VISION:
            return PerceptionDecision(route, quality, "visual reasoning required" if requires_visual_reasoning else "OCR quality is insufficient")
        return PerceptionDecision(route, quality, "OCR text is sufficient" if quality is OcrQuality.HIGH else "vision unavailable; text fallback")
