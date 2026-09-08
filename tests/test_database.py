from datetime import UTC, datetime

import pytest

from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.models import Assignment, Course, OverrideType, ScheduleOverride
from university_ai.database.repository import AssignmentRepository, CourseRepository, ScheduleOverrideRepository


@pytest.fixture
def connection(tmp_path):
    database = Database(tmp_path / "data.sqlite3")
    connection = database.connect()
    migrate(connection)
    yield connection
    database.stop()


def test_course_and_timezone_aware_assignment_are_persisted(connection):
    course = CourseRepository(connection).create(Course(None, "Control", 0, "10:00", "11:30", "Asia/Tokyo"))
    assignment = AssignmentRepository(connection).create(Assignment(None, course.id, "Report", datetime(2026, 9, 9, 3, tzinfo=UTC)))
    assert course.id is not None
    assert assignment.id is not None
    assert connection.execute("SELECT due_at FROM assignments").fetchone()[0].endswith("Z")


def test_naive_absolute_time_is_rejected(connection):
    course = CourseRepository(connection).create(Course(None, "Control", 0, "10:00", "11:30", "Asia/Tokyo"))
    with pytest.raises(ValueError):
        AssignmentRepository(connection).create(Assignment(None, course.id, "Report", datetime(2026, 9, 9, 3)))


def test_foreign_key_and_override_uniqueness_are_enforced(connection):
    with pytest.raises(Exception):
        ScheduleOverrideRepository(connection).create(ScheduleOverride(None, 999, "2026-09-14", OverrideType.CANCEL))
    course = CourseRepository(connection).create(Course(None, "Control", 0, "10:00", "11:30", "Asia/Tokyo"))
    repository = ScheduleOverrideRepository(connection)
    repository.create(ScheduleOverride(None, course.id, "2026-09-14", OverrideType.CANCEL))
    with pytest.raises(Exception):
        repository.create(ScheduleOverride(None, course.id, "2026-09-14", OverrideType.CANCEL))
