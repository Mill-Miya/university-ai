from datetime import UTC, datetime
import sqlite3

import pytest

from university_ai.core.context import ContextEngine
from university_ai.core.rules import NotificationCandidate, RuleEngine
from university_ai.database.database import Database
from university_ai.database.migrations import MIGRATIONS, migrate
from university_ai.database.models import Assignment, Course, NotificationEvent, NotificationStatus
from university_ai.database.repository import (
    AssignmentRepository, CourseRepository, ExamRepository, NotificationEventRepository, ScheduleOverrideRepository,
)
from university_ai.notification.fallback import FallbackOnErrorAdapter, TrayFallbackAdapter
from university_ai.notification.service import NotificationService
from university_ai.notification.windows import WindowsToastAdapter


class RecordingAdapter:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent = []

    def send(self, candidate) -> None:
        if self.error:
            raise self.error
        self.sent.append(candidate)


@pytest.fixture
def database_and_events(tmp_path):
    database = Database(tmp_path / "data.sqlite3")
    connection = database.connect()
    migrate(connection)
    yield database, connection, NotificationEventRepository(connection)
    database.stop()


def candidate(subject_id: int = 1) -> NotificationCandidate:
    return NotificationCandidate(
        "course_start", "course", subject_id, datetime(2026, 9, 14, 0, 30, tzinfo=UTC), "Course", "Control starts soon"
    )


def test_migration_adds_notification_events_to_existing_v1_database(tmp_path):
    database = Database(tmp_path / "existing.sqlite3")
    connection = database.connect()
    connection.executescript(MIGRATIONS[0][1])
    connection.execute("INSERT INTO schema_version(version) VALUES (1)")
    connection.commit()
    migrate(connection)
    assert connection.execute("SELECT version FROM schema_version").fetchone()[0] == 4
    assert connection.execute("SELECT name FROM sqlite_master WHERE name='notification_events'").fetchone() is not None
    migrate(connection)
    database.stop()


def test_event_repository_state_changes_utc_and_naive_rejection(database_and_events):
    _, _, events = database_and_events
    saved = events.create(NotificationEvent(None, "course_start", "course", 1, candidate().scheduled_at))
    assert saved.status == NotificationStatus.PENDING
    delivered_at = datetime(2026, 9, 14, 0, 31, tzinfo=UTC)
    delivered = events.update_status(saved.id, NotificationStatus.DELIVERED, delivered_at=delivered_at)
    assert delivered.delivered_at == delivered_at
    assert events.update_status(saved.id, NotificationStatus.FAILED).status == NotificationStatus.FAILED
    assert events.update_status(saved.id, NotificationStatus.SUPPRESSED).status == NotificationStatus.SUPPRESSED
    with pytest.raises(ValueError):
        events.create(NotificationEvent(None, "course_start", "course", 2, datetime(2026, 9, 14, 0, 30)))
    with pytest.raises(ValueError):
        events.update_status(saved.id, NotificationStatus.DELIVERED)


def test_unique_identity_is_persistent_deduplication(database_and_events):
    database, _, events = database_and_events
    first, created = events.create_if_absent(NotificationEvent(None, "course_start", "course", 1, candidate().scheduled_at))
    assert created
    database.stop()  # Simulate application shutdown.
    reopened = Database(database._path)
    connection = reopened.connect()
    migrate(connection)
    second, created = NotificationEventRepository(connection).create_if_absent(
        NotificationEvent(None, "course_start", "course", 1, candidate().scheduled_at)
    )
    assert not created and second.id == first.id
    assert connection.execute("SELECT COUNT(*) FROM notification_events").fetchone()[0] == 1
    reopened.stop()


def test_service_marks_delivered_failed_suppressed_and_does_not_redeliver(database_and_events):
    _, _, events = database_and_events
    adapter = RecordingAdapter()
    service = NotificationService(events, adapter)
    delivered = service.process([candidate()])
    assert delivered[0].status == NotificationStatus.DELIVERED
    assert delivered[0].delivered_at is not None and len(adapter.sent) == 1
    duplicate = service.process([candidate()])
    assert duplicate[0].id == delivered[0].id and len(adapter.sent) == 1
    failed = NotificationService(events, RecordingAdapter(RuntimeError("toast failed"))).process([candidate(2)])
    assert failed[0].status == NotificationStatus.FAILED
    suppressed = service.process([candidate(3)], should_deliver=lambda _: False)
    assert suppressed[0].status == NotificationStatus.SUPPRESSED


def test_service_handles_database_error_without_stopping():
    class BrokenEvents:
        def create_if_absent(self, event):
            raise sqlite3.OperationalError("disk unavailable")

    adapter = RecordingAdapter()
    assert NotificationService(BrokenEvents(), adapter).process([candidate()]) == []
    assert adapter.sent == []


def test_windows_and_fallback_adapters_are_replaceable():
    messages = []
    WindowsToastAdapter(lambda title, body: messages.append(("windows", title, body))).send(candidate())
    TrayFallbackAdapter(lambda title, body: messages.append(("tray", title, body))).send(candidate())
    fallback = TrayFallbackAdapter(lambda title, body: messages.append(("fallback", title, body)))
    FallbackOnErrorAdapter(WindowsToastAdapter(lambda *_: (_ for _ in ()).throw(RuntimeError("toast failed"))), fallback).send(candidate())
    assert [message[0] for message in messages] == ["windows", "tray", "fallback"]


def test_rule_candidate_flows_through_service_to_durable_delivery(database_and_events):
    _, connection, events = database_and_events
    courses = CourseRepository(connection)
    assignments = AssignmentRepository(connection)
    course = courses.create(Course(None, "Control", 0, "10:00", "11:30", "Asia/Tokyo"))
    assignments.create(Assignment(None, course.id, "Report", datetime(2026, 9, 15, 0, 30, tzinfo=UTC)))
    context = ContextEngine(courses, assignments, ExamRepository(connection), ScheduleOverrideRepository(connection)).build(
        datetime(2026, 9, 14, 0, 30, tzinfo=UTC)
    )
    candidates = RuleEngine().evaluate(context)
    adapter = RecordingAdapter()
    events_after_delivery = NotificationService(events, adapter).process(candidates)
    assert {event.status for event in events_after_delivery} == {NotificationStatus.DELIVERED}
    assert len(events_after_delivery) == len(adapter.sent) == 2
