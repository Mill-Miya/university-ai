from datetime import UTC, datetime

import pytest

from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.models import Assignment, AssignmentStatus, Course, Exam, OverrideType, ScheduleOverride
from university_ai.database.repository import AssignmentRepository, CourseRepository, ExamRepository, ScheduleOverrideRepository


@pytest.fixture
def repositories(tmp_path):
    database = Database(tmp_path / "data.sqlite3")
    connection = database.connect()
    migrate(connection)
    yield (
        CourseRepository(connection),
        AssignmentRepository(connection),
        ExamRepository(connection),
        ScheduleOverrideRepository(connection),
    )
    database.stop()


def course(name: str = "Control") -> Course:
    return Course(None, name, 0, "10:00", "11:30", "Asia/Tokyo", classroom="A101")


def test_course_crud_and_validation(repositories):
    courses, _, _, _ = repositories
    saved = courses.create(course())
    assert courses.get(saved.id) == saved
    changed = courses.update(Course(saved.id, "Advanced Control", 1, "13:00", "14:30", "Asia/Tokyo"))
    assert courses.get(saved.id) == changed
    assert courses.delete(saved.id) is True
    assert courses.get(saved.id) is None
    with pytest.raises(ValueError):
        courses.create(Course(None, "Broken", 7, "10:00", "11:30", "Asia/Tokyo"))
    with pytest.raises(ValueError):
        courses.create(Course(None, "Broken", 0, "11:30", "10:00", "Invalid/Timezone"))


def test_assignment_crud_and_utc_round_trip(repositories):
    courses, assignments, _, _ = repositories
    saved_course = courses.create(course())
    saved = assignments.create(Assignment(None, saved_course.id, "Report", datetime(2026, 9, 9, 12, tzinfo=UTC)))
    loaded = assignments.get(saved.id)
    assert loaded is not None and loaded.due_at.tzinfo == UTC
    assignments.update(Assignment(saved.id, saved_course.id, "Final report", datetime(2026, 9, 10, 12, tzinfo=UTC), AssignmentStatus.DONE))
    assert assignments.get(saved.id).status == AssignmentStatus.DONE
    assert assignments.list(include_finished=False) == []
    assert assignments.delete(saved.id) is True
    with pytest.raises(ValueError):
        assignments.create(Assignment(None, saved_course.id, "Naive", datetime(2026, 9, 9, 12)))


def test_exam_crud_and_timezone_validation(repositories):
    courses, _, exams, _ = repositories
    saved_course = courses.create(course())
    saved = exams.create(Exam(None, saved_course.id, "Midterm", datetime(2026, 10, 1, 3, tzinfo=UTC)))
    assert exams.get(saved.id) == saved
    changed = exams.update(Exam(saved.id, saved_course.id, "Final", datetime(2026, 11, 1, 3, tzinfo=UTC), scope="Chapters 1-5"))
    assert exams.get(saved.id) == changed
    assert exams.delete(saved.id) is True
    with pytest.raises(ValueError):
        exams.create(Exam(None, saved_course.id, "Naive", datetime(2026, 10, 1, 3)))


def test_schedule_override_crud_and_rules(repositories):
    courses, _, _, overrides = repositories
    saved_course = courses.create(course())
    cancelled = overrides.create(ScheduleOverride(None, saved_course.id, "2026-09-14", OverrideType.CANCEL))
    makeup = overrides.create(ScheduleOverride(None, saved_course.id, "2026-09-20", OverrideType.MAKEUP, "09:00", "10:30"))
    assert overrides.list_for_course(saved_course.id) == [cancelled, makeup]
    changed = overrides.update(ScheduleOverride(makeup.id, saved_course.id, "2026-09-21", OverrideType.CHANGE, "11:00", "12:30"))
    assert overrides.get(makeup.id) == changed
    assert overrides.delete(cancelled.id) is True
    with pytest.raises(ValueError):
        overrides.create(ScheduleOverride(None, saved_course.id, "bad-date", OverrideType.CANCEL))
    with pytest.raises(ValueError):
        overrides.create(ScheduleOverride(None, saved_course.id, "2026-09-22", OverrideType.MAKEUP))


def test_deleting_course_with_dependents_is_rejected(repositories):
    courses, assignments, _, _ = repositories
    saved_course = courses.create(course())
    assignments.create(Assignment(None, saved_course.id, "Report", datetime(2026, 9, 9, 12, tzinfo=UTC)))
    with pytest.raises(Exception):
        courses.delete(saved_course.id)
