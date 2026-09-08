from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from collections.abc import Callable

from university_ai.core.context import UniversityContext


@dataclass(frozen=True)
class NotificationCandidate:
    rule_key: str
    subject_type: str
    subject_id: int
    scheduled_at: datetime
    title: str
    body: str


@dataclass(frozen=True)
class RuleConfiguration:
    course_before: timedelta = timedelta(minutes=30)
    assignment_before: timedelta = timedelta(hours=24)
    exam_before: timedelta = timedelta(hours=24)
    evaluation_window: timedelta = timedelta(minutes=1)
    course_enabled: bool = True
    assignment_enabled: bool = True
    exam_enabled: bool = True


class RuleEngine:
    """Calculates notification candidates; persistence and delivery are Phase 5 concerns."""

    def __init__(
        self, configuration: RuleConfiguration | None = None, *, configuration_provider: Callable[[], RuleConfiguration] | None = None
    ) -> None:
        self._configuration = configuration or RuleConfiguration()
        self._configuration_provider = configuration_provider

    def evaluate(self, context: UniversityContext) -> list[NotificationCandidate]:
        now = self._require_aware(context.current_datetime)
        configuration = self._configuration_provider() if self._configuration_provider else self._configuration
        candidates: list[NotificationCandidate] = []
        for occurrence in context.today_courses if configuration.course_enabled else ():
            scheduled = occurrence.start_at - configuration.course_before
            if self._is_due(now, scheduled):
                candidates.append(NotificationCandidate(
                    "course_start", "course", occurrence.course.id, scheduled,
                    f"授業まで{int(configuration.course_before.total_seconds() // 60)}分",
                    f"{occurrence.course.name} がまもなく開始します。",
                ))
        for assignment in context.upcoming_assignments if configuration.assignment_enabled else ():
            scheduled = assignment.due_at - configuration.assignment_before
            if self._is_due(now, scheduled):
                candidates.append(NotificationCandidate(
                    "assignment_due", "assignment", assignment.id, scheduled,
                    "課題期限が近づいています", f"{assignment.title} の期限が24時間後です。",
                ))
        for exam in context.upcoming_exams if configuration.exam_enabled else ():
            scheduled = exam.start_at - configuration.exam_before
            if self._is_due(now, scheduled):
                candidates.append(NotificationCandidate(
                    "exam_start", "exam", exam.id, scheduled,
                    "試験開始が近づいています", f"{exam.title} は24時間後です。",
                ))
        return candidates

    def _is_due(self, now: datetime, scheduled: datetime) -> bool:
        return scheduled <= now < scheduled + self._configuration.evaluation_window

    @staticmethod
    def _require_aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware datetime required")
        return value.astimezone(UTC)
