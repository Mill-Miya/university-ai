from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from university_ai.core.context import ContextEngine
from university_ai.database.repository import CourseRepository


class UniversityPresenter:
    """Headless presentation data; Qt widgets never query SQLite directly."""

    def __init__(self, context_engine: ContextEngine, courses: CourseRepository, *, timezone: str = "Asia/Tokyo") -> None:
        self._context_engine = context_engine
        self._courses = courses
        self._timezone = ZoneInfo(timezone)

    def today_courses(self, now: datetime | None = None) -> list[str]:
        context = self._context_engine.build(now or datetime.now(UTC))
        return [
            f"{item.start_at.astimezone(self._timezone):%H:%M} {item.course.name} ({item.classroom or '-'})"
            for item in context.today_courses
        ]

    def assignments(self, now: datetime | None = None) -> list[str]:
        context = self._context_engine.build(now or datetime.now(UTC))
        names = {course.id: course.name for course in self._courses.list()}
        return [
            f"{names.get(item.course_id, '-')} | {item.title} | {item.due_at.astimezone(self._timezone):%Y-%m-%d %H:%M} | {item.status} | {item.priority or '-'}"
            for item in context.upcoming_assignments
        ]

    def exams(self, now: datetime | None = None) -> list[str]:
        context = self._context_engine.build(now or datetime.now(UTC))
        names = {course.id: course.name for course in self._courses.list()}
        return [
            f"{names.get(item.course_id, '-')} | {item.title} | {item.start_at.astimezone(self._timezone):%Y-%m-%d %H:%M} | {item.classroom or '-'} | {item.scope or '-'}"
            for item in context.upcoming_exams
        ]
