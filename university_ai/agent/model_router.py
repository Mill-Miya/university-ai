from __future__ import annotations

from university_ai.agent.models import Intent, ModelRoute


class ModelRouter:
    """Routing classification only. Backend/model switching starts in Phase 2."""

    _RULE_ONLY = frozenset({Intent.TASK_QUERY, Intent.EXAM_QUERY, Intent.COURSE_QUERY, Intent.SCHEDULE_QUERY})
    _VISION = frozenset({Intent.SCREEN_EXPLAIN, Intent.SCREEN_TRANSLATE, Intent.SCREEN_SUMMARIZE})

    def route(self, intent: Intent, *, ocr_quality=None, requires_visual_reasoning: bool = False,
              vision_available: bool = True) -> ModelRoute:
        if intent in self._RULE_ONLY:
            return ModelRoute.RULE_ONLY
        if intent in self._VISION:
            quality = getattr(ocr_quality, "value", ocr_quality)
            if not vision_available or (quality == "HIGH" and not requires_visual_reasoning):
                return ModelRoute.FAST
            return ModelRoute.FAST_VISION
        return ModelRoute.FAST
