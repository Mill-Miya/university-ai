from __future__ import annotations

from university_ai.agent.models import ToolResult
from university_ai.agent.tools.registry import Tool


def document_tools(rag_service) -> list[Tool]:
    def search(arguments: dict) -> ToolResult:
        response = rag_service.answer(arguments["question"])
        return ToolResult(response.answer, {"sources": response.sources, "abstained": response.abstained, "model": response.model})
    return [Tool("search_documents", "取り込み済み資料を検索して根拠付きで回答する", frozenset({"question"}), search)]
