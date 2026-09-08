from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from university_ai.database.models import Assignment, Course, Exam, OverrideType, ScheduleOverride
from university_ai.database.repository import AssignmentRepository, CourseRepository, ExamRepository, ScheduleOverrideRepository


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class CourseOccurrence:
    course: Course
    date: date
    start_at: datetime
    end_at: datetime
    classroom: str | None
    override: ScheduleOverride | None = None


@dataclass(frozen=True)
class UniversityContext:
    current_datetime: datetime
    timezone: str
    weekday: int
    today_courses: tuple[CourseOccurrence, ...]
    upcoming_assignments: tuple[Assignment, ...]
    upcoming_exams: tuple[Exam, ...]
    schedule_overrides: tuple[ScheduleOverride, ...]


class ContextEngine:
    """Builds deterministic, read-only university context from repositories."""

    def __init__(
        self,
        courses: CourseRepository,
        assignments: AssignmentRepository,
        exams: ExamRepository,
        overrides: ScheduleOverrideRepository,
        *,
        timezone: str = "Asia/Tokyo",
    ) -> None:
        self._courses = courses
        self._assignments = assignments
        self._exams = exams
        self._overrides = overrides
        self._timezone = ZoneInfo(timezone)

    def build(self, current_datetime: datetime) -> UniversityContext:
        now = _require_aware(current_datetime)
        occurrences: list[CourseOccurrence] = []
        all_overrides: list[ScheduleOverride] = []
        for course in self._courses.list():
            course_date = now.astimezone(ZoneInfo(course.timezone)).date()
            course_overrides = self._overrides.list_for_course(course.id)
            all_overrides.extend(course_overrides)
            occurrences.extend(self._occurrences_for_date(course, course_date, course_overrides))

        local_date = now.astimezone(self._timezone).date()
        return UniversityContext(
            current_datetime=now,
            timezone=self._timezone.key,
            weekday=local_date.weekday(),
            today_courses=tuple(sorted(occurrences, key=lambda occurrence: occurrence.start_at)),
            upcoming_assignments=tuple(self._assignments.list(include_finished=False)),
            upcoming_exams=tuple(self._exams.list()),
            schedule_overrides=tuple(all_overrides),
        )

    @staticmethod
    def _occurrences_for_date(
        course: Course, target_date: date, overrides: list[ScheduleOverride]
    ) -> list[CourseOccurrence]:
        relevant = [override for override in overrides if override.date == target_date.isoformat()]
        occurrences: list[CourseOccurrence] = []
        normal = target_date.weekday() == course.weekday
        changed_or_cancelled = any(item.type in (OverrideType.CANCEL, OverrideType.CHANGE) for item in relevant)
        if normal and not changed_or_cancelled:
            occurrences.append(ContextEngine._occurrence(course, target_date, course.start_time, course.end_time, course.classroom))
        for override in relevant:
            if override.type in (OverrideType.MAKEUP, OverrideType.CHANGE):
                occurrences.append(ContextEngine._occurrence(
                    course, target_date, override.start_time, override.end_time, override.classroom or course.classroom, override
                ))
        return occurrences

    @staticmethod
    def _occurrence(
        course: Course, target_date: date, start_time: str | None, end_time: str | None,
        classroom: str | None, override: ScheduleOverride | None = None,
    ) -> CourseOccurrence:
        assert start_time is not None and end_time is not None
        zone = ZoneInfo(course.timezone)
        start = datetime.combine(target_date, time.fromisoformat(start_time), tzinfo=zone).astimezone(UTC)
        end = datetime.combine(target_date, time.fromisoformat(end_time), tzinfo=zone).astimezone(UTC)
        return CourseOccurrence(course, target_date, start, end, classroom, override)
