from datetime import UTC, datetime
from threading import Thread

import pytest

from university_ai.core.context import ContextEngine
from university_ai.core.rules import RuleEngine
from university_ai.core.scheduler import UniversityScheduler
from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.models import Assignment, AssignmentStatus, Course, Exam, OverrideType, ScheduleOverride
from university_ai.database.repository import AssignmentRepository, CourseRepository, ExamRepository, ScheduleOverrideRepository


@pytest.fixture
def services(tmp_path):
    database = Database(tmp_path / "data.sqlite3")
    connection = database.connect()
    migrate(connection)
    courses = CourseRepository(connection)
    assignments = AssignmentRepository(connection)
    exams = ExamRepository(connection)
    overrides = ScheduleOverrideRepository(connection)
    yield database, courses, assignments, exams, overrides, ContextEngine(courses, assignments, exams, overrides)
    database.stop()


def add_course(courses, *, timezone="Asia/Tokyo", weekday=0, start="10:00"):
    return courses.create(Course(None, "Control", weekday, start, "11:30", timezone, classroom="A101"))


def test_course_candidate_is_generated_at_exact_notification_boundary(services):
    _, courses, _, _, _, context_engine = services
    add_course(courses)
    context = context_engine.build(datetime(2026, 9, 14, 0, 30, tzinfo=UTC))  # Monday 09:30 JST
    candidates = RuleEngine().evaluate(context)
    assert [(item.rule_key, item.subject_type) for item in candidates] == [("course_start", "course")]
    assert candidates[0].scheduled_at == datetime(2026, 9, 14, 0, 30, tzinfo=UTC)


def test_course_candidate_respects_evaluation_window_boundary(services):
    _, courses, _, _, _, context_engine = services
    add_course(courses)
    assert RuleEngine().evaluate(context_engine.build(datetime(2026, 9, 14, 0, 29, 59, tzinfo=UTC))) == []
    assert RuleEngine().evaluate(context_engine.build(datetime(2026, 9, 14, 0, 31, tzinfo=UTC))) == []


def test_cancel_suppresses_normal_course(services):
    _, courses, _, _, overrides, context_engine = services
    course = add_course(courses)
    overrides.create(ScheduleOverride(None, course.id, "2026-09-14", OverrideType.CANCEL))
    assert context_engine.build(datetime(2026, 9, 14, 0, 30, tzinfo=UTC)).today_courses == ()


def test_makeup_and_change_replace_schedule_correctly(services):
    _, courses, _, _, overrides, context_engine = services
    course = add_course(courses)
    overrides.create(ScheduleOverride(None, course.id, "2026-09-20", OverrideType.MAKEUP, "09:00", "10:30"))
    makeup = context_engine.build(datetime(2026, 9, 20, 0, 0, tzinfo=UTC)).today_courses
    assert len(makeup) == 1 and makeup[0].override.type == OverrideType.MAKEUP
    overrides.create(ScheduleOverride(None, course.id, "2026-09-14", OverrideType.CHANGE, "12:00", "13:30"))
    changed = context_engine.build(datetime(2026, 9, 14, 2, 30, tzinfo=UTC)).today_courses
    assert len(changed) == 1 and changed[0].start_at == datetime(2026, 9, 14, 3, 0, tzinfo=UTC)
    assert changed[0].override.type == OverrideType.CHANGE


def test_assignment_and_exam_candidates_exclude_finished_assignments(services):
    _, courses, assignments, exams, _, context_engine = services
    course = add_course(courses)
    due = datetime(2026, 9, 15, 0, 30, tzinfo=UTC)
    assignments.create(Assignment(None, course.id, "Active", due))
    assignments.create(Assignment(None, course.id, "Done", due, AssignmentStatus.DONE))
    assignments.create(Assignment(None, course.id, "Cancelled", due, AssignmentStatus.CANCELLED))
    exams.create(Exam(None, course.id, "Midterm", due))
    candidates = RuleEngine().evaluate(context_engine.build(datetime(2026, 9, 14, 0, 30, tzinfo=UTC)))
    assert {(item.rule_key, item.subject_type) for item in candidates} == {("course_start", "course"), ("assignment_due", "assignment"), ("exam_start", "exam")}


def test_course_timezone_is_used_for_occurrence_and_rule_evaluation(services):
    _, courses, _, _, _, context_engine = services
    add_course(courses, timezone="America/New_York")
    # 13:30 UTC is 09:30 EDT; the local course starts at 10:00 on Monday.
    candidates = RuleEngine().evaluate(context_engine.build(datetime(2026, 9, 14, 13, 30, tzinfo=UTC)))
    assert len(candidates) == 1 and candidates[0].rule_key == "course_start"


def test_naive_datetime_is_rejected(services):
    _, _, _, _, _, context_engine = services
    with pytest.raises(ValueError):
        context_engine.build(datetime(2026, 9, 14, 0, 30))


def test_scheduler_starts_stops_and_reads_registered_services(services):
    _, courses, _, _, _, context_engine = services
    add_course(courses)
    delivered = []
    scheduler = UniversityScheduler(context_engine, RuleEngine(), delivered.append, interval_seconds=3600)
    scheduler.run_once()
    assert delivered and delivered[0] == []
    scheduler.start()
    assert scheduler.running
    scheduler.stop()
    assert not scheduler.running


def test_scheduler_can_evaluate_database_from_a_background_thread(services):
    _, courses, _, _, _, context_engine = services
    add_course(courses)
    delivered = []
    scheduler = UniversityScheduler(context_engine, RuleEngine(), delivered.append)
    thread = Thread(target=scheduler.run_once)
    thread.start(); thread.join(timeout=2)
    assert not thread.is_alive()
    assert delivered == [[]]
