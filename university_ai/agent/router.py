from __future__ import annotations

from university_ai.agent.models import AgentRequest, Intent


class IntentRouter:
    """Deterministic first-pass intent classifier; no model runtime dependency."""

    def route(self, request: AgentRequest) -> Intent:
        if request.explicit_intent is not None:
            return request.explicit_intent
        text = request.text.strip().lower()
        if any(word in text for word in ("課題", "提出物", "レポート")):
            return Intent.TASK_QUERY
        if any(word in text for word in ("試験", "テスト", "exam")):
            return Intent.EXAM_QUERY
        if any(word in text for word in ("資料", "document", "pdf")):
            return Intent.DOCUMENT_SEARCH
        if any(word in text for word in ("時間割", "今日の授業", "次の授業", "授業")):
            return Intent.SCHEDULE_QUERY
        return Intent.CHAT
