from __future__ import annotations

import logging
from pathlib import Path
from datetime import timedelta

from PySide6.QtWidgets import QApplication

from university_ai.app.config import AppConfig, SettingsStore
from university_ai.app.lifecycle import ApplicationLifecycle
from university_ai.app.startup import WindowsStartupAdapter
from university_ai.core.context import ContextEngine
from university_ai.core.rules import RuleConfiguration, RuleEngine
from university_ai.core.scheduler import UniversityScheduler
from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.repository import (
    AssignmentRepository, CourseRepository, ExamRepository, NotificationEventRepository, ScheduleOverrideRepository,
)
from university_ai.notification.fallback import FallbackOnErrorAdapter, TrayFallbackAdapter
from university_ai.notification.service import NotificationService
from university_ai.notification.windows import WindowsToastAdapter
from university_ai.ui.presenter import UniversityPresenter
from university_ai.ui.settings import SettingsDialog
from university_ai.ui.tray import SystemTrayController


def configure_logging(config: AppConfig) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(config.log_dir / "university_ai.log", encoding="utf-8")],
    )


def _rule_configuration(store: SettingsStore) -> RuleConfiguration:
    settings = store.load()
    return RuleConfiguration(
        course_before=timedelta(minutes=settings.course_minutes),
        assignment_before=timedelta(minutes=settings.assignment_minutes),
        exam_before=timedelta(minutes=settings.exam_minutes),
        course_enabled=settings.course_notifications,
        assignment_enabled=settings.assignment_notifications,
        exam_enabled=settings.exam_notifications,
    )


def configure_resident_qt_application(app: QApplication) -> None:
    """A Tray-resident application must not exit merely because a dialog closes."""
    app.setQuitOnLastWindowClosed(False)


def build_resident_application(config: AppConfig):
    """Compose MVP 1 components. UI adapters are the only Windows/Qt boundary."""
    database = Database(config.database_path)
    connection = database.connect(); migrate(connection)
    courses = CourseRepository(connection); assignments = AssignmentRepository(connection); exams = ExamRepository(connection)
    overrides = ScheduleOverrideRepository(connection); events = NotificationEventRepository(connection)
    settings = SettingsStore(config.settings_path); startup = WindowsStartupAdapter()
    context = ContextEngine(courses, assignments, exams, overrides)
    rules = RuleEngine(configuration_provider=lambda: _rule_configuration(settings))
    app = QApplication.instance() or QApplication([])
    configure_resident_qt_application(app)
    lifecycle_holder = {}
    presenter = UniversityPresenter(context, courses)
    tray = SystemTrayController(
        presenter, lambda: SettingsDialog(settings, startup), lambda: lifecycle_holder["lifecycle"].stop() or app.quit()
    )
    adapter = FallbackOnErrorAdapter(WindowsToastAdapter(), TrayFallbackAdapter(tray.show_message))
    service = NotificationService(events, adapter)
    scheduler = UniversityScheduler(context, rules, service)
    lifecycle = ApplicationLifecycle(tray, scheduler, database)
    lifecycle_holder["lifecycle"] = lifecycle
    return app, tray, scheduler, lifecycle


def main(root: Path | None = None, *, run_event_loop: bool | None = None) -> int:
    config = AppConfig.default(root)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(config)
    logging.getLogger(__name__).info("University AI starting")
    if run_event_loop is None:
        run_event_loop = root is None
    if not run_event_loop:
        return 0
    try:
        app, tray, scheduler, lifecycle = build_resident_application(config)
        if not tray.start():
            logging.getLogger(__name__).error("University AI cannot run without System Tray")
            lifecycle.stop()
            return 1
        scheduler.start()
        result = app.exec()
        lifecycle.stop()
        return result
    except Exception:
        logging.getLogger(__name__).exception("University AI resident startup failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
