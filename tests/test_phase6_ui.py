import json
from datetime import UTC, datetime

import pytest

from university_ai.app.config import AppConfig, SettingsStore, UserSettings
from university_ai.app.main import _rule_configuration
from university_ai.app.startup import WindowsStartupAdapter
from university_ai.core.context import ContextEngine
from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.models import Assignment, AssignmentStatus, Course, Exam, OverrideType, ScheduleOverride
from university_ai.database.repository import AssignmentRepository, CourseRepository, ExamRepository, ScheduleOverrideRepository
from university_ai.notification.fallback import FallbackOnErrorAdapter, TrayFallbackAdapter
from university_ai.notification.windows import WindowsToastAdapter
from university_ai.ui.presenter import UniversityPresenter
from university_ai.ui.tray import SystemTrayController


@pytest.fixture
def presenter(tmp_path):
    database = Database(tmp_path / "data.sqlite3")
    connection = database.connect(); migrate(connection)
    courses = CourseRepository(connection); assignments = AssignmentRepository(connection); exams = ExamRepository(connection)
    overrides = ScheduleOverrideRepository(connection)
    course = courses.create(Course(None, "Control", 0, "10:00", "11:30", "Asia/Tokyo", classroom="A101"))
    assignments.create(Assignment(None, course.id, "Active", datetime(2026, 9, 15, 0, 30, tzinfo=UTC), priority="HIGH"))
    assignments.create(Assignment(None, course.id, "Done", datetime(2026, 9, 15, 0, 30, tzinfo=UTC), AssignmentStatus.DONE))
    assignments.create(Assignment(None, course.id, "Cancelled", datetime(2026, 9, 15, 0, 30, tzinfo=UTC), AssignmentStatus.CANCELLED))
    exams.create(Exam(None, course.id, "Midterm", datetime(2026, 9, 20, 0, 0, tzinfo=UTC), "B201", "Ch. 1-5"))
    yield UniversityPresenter(ContextEngine(courses, assignments, exams, overrides), courses), course, overrides
    database.stop()


def test_presenter_uses_context_for_courses_assignments_exams_and_timezone(presenter):
    view, _, _ = presenter
    now = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)  # Monday JST
    assert view.today_courses(now) == ["10:00 Control (A101)"]
    assert len(view.assignments(now)) == 1 and "Active" in view.assignments(now)[0] and "09:30" in view.assignments(now)[0]
    assert "Midterm" in view.exams(now)[0] and "09:00" in view.exams(now)[0]


def test_presenter_reflects_cancel_makeup_and_change(presenter):
    view, course, overrides = presenter
    overrides.create(ScheduleOverride(None, course.id, "2026-09-14", OverrideType.CANCEL))
    assert view.today_courses(datetime(2026, 9, 14, 0, 0, tzinfo=UTC)) == []
    overrides.create(ScheduleOverride(None, course.id, "2026-09-20", OverrideType.MAKEUP, "09:00", "10:30", "C101"))
    assert view.today_courses(datetime(2026, 9, 20, 0, 0, tzinfo=UTC)) == ["09:00 Control (C101)"]
    overrides.create(ScheduleOverride(None, course.id, "2026-09-21", OverrideType.CHANGE, "12:00", "13:30", "D101"))
    assert view.today_courses(datetime(2026, 9, 21, 0, 0, tzinfo=UTC)) == ["12:00 Control (D101)"]


def test_settings_persist_reload_fallback_and_drive_rule_configuration(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    settings = UserSettings(False, True, False, 15, 90, 120, True)
    store.save(settings)
    assert store.load() == settings
    rule = _rule_configuration(store)
    assert not rule.course_enabled and rule.assignment_enabled and rule.assignment_before.total_seconds() == 5400
    store._path.write_text(json.dumps({"course_notifications": "bad"}), encoding="utf-8")
    assert store.load() == UserSettings()


def test_startup_adapter_is_idempotent_and_safe(tmp_path):
    startup = WindowsStartupAdapter(startup_directory=tmp_path)
    assert not startup.enabled()
    assert startup.enable() and startup.enable() and startup.enabled()
    assert startup.disable() and startup.disable() and not startup.enabled()


def test_tray_unavailable_and_tray_fallback_failure_do_not_escape_core():
    tray = SystemTrayController(None, lambda: None, lambda: None, system_tray_available=lambda: False)
    assert tray.start() is False
    adapter = FallbackOnErrorAdapter(WindowsToastAdapter(lambda *_: (_ for _ in ()).throw(RuntimeError("toast"))), TrayFallbackAdapter())
    with pytest.raises(RuntimeError):
        adapter.send(type("Candidate", (), {"title": "T", "body": "B"})())
