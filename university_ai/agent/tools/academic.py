from __future__ import annotations

from university_ai.agent.models import ToolResult
from university_ai.agent.tools.registry import Tool


def academic_tools(presenter) -> list[Tool]:
    """Delegate display-safe, deterministic queries to the existing presenter."""
    return [
        Tool("get_schedule", "今日の授業予定を取得する", frozenset(), lambda _args: ToolResult("\n".join(presenter.today_courses()) or "今日の授業はありません。")),
        Tool("get_assignments", "未完了課題を取得する", frozenset(), lambda _args: ToolResult("\n".join(presenter.assignments()) or "未完了の課題はありません。")),
        Tool("get_exams", "試験予定を取得する", frozenset(), lambda _args: ToolResult("\n".join(presenter.exams()) or "試験予定はありません。")),
    ]
