from __future__ import annotations

import logging
from pathlib import Path
from datetime import timedelta

from PySide6.QtWidgets import QApplication, QMessageBox

from university_ai.app.config import AppConfig, SettingsStore
from university_ai.app.lifecycle import ApplicationLifecycle
from university_ai.app.commands import ApplicationCommandDispatcher
from university_ai.app.startup import WindowsStartupAdapter
from university_ai.core.context import ContextEngine
from university_ai.core.rules import RuleConfiguration, RuleEngine
from university_ai.core.scheduler import UniversityScheduler
from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.repository import (
    AssignmentRepository, CourseRepository, DocumentRepository, ExamRepository, NotificationEventRepository,
    OcrResultRepository, ScheduleOverrideRepository, ScreenCaptureRepository,
)
from university_ai.capture.backend import QtScreenCaptureBackend
from university_ai.capture.service import CaptureStorageService, ScreenCaptureService
from university_ai.documents.import_service import DocumentImportService
from university_ai.ocr.engine import TesseractOcrEngine
from university_ai.ocr.service import OcrService
from university_ai.llm.ollama import OllamaEngine
from university_ai.llm.service import LlmService
from university_ai.ui.llm import AiQuestionDialog
from university_ai.notification.fallback import FallbackOnErrorAdapter, TrayFallbackAdapter
from university_ai.notification.registration import WindowsToastRegistration
from university_ai.notification.service import NotificationService
from university_ai.notification.windows import WindowsToastAdapter
from university_ai.ui.presenter import UniversityPresenter
from university_ai.ui.documents import DocumentPresenter, DocumentsDialog
from university_ai.ui.settings import SettingsDialog
from university_ai.ui.tray import SystemTrayController
from university_ai.ui.capture import ScreenCaptureController
from university_ai.overlay import NovaOverlayAdapter, NovaOverlayClient


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
    overrides = ScheduleOverrideRepository(connection); events = NotificationEventRepository(connection); documents = DocumentRepository(connection)
    captures = ScreenCaptureRepository(connection); ocr_results = OcrResultRepository(connection)
    settings = SettingsStore(config.settings_path); startup = WindowsStartupAdapter()
    toast_registration = WindowsToastRegistration(project_root=config.data_dir.parent)
    if not toast_registration.register():
        logging.getLogger(__name__).warning("Windows Toast registration unavailable; Tray fallback remains available")
    elif not toast_registration.apply_to_current_process():
        logging.getLogger(__name__).warning("Windows Toast process AUMID unavailable; Tray fallback remains available")
    context = ContextEngine(courses, assignments, exams, overrides)
    rules = RuleEngine(configuration_provider=lambda: _rule_configuration(settings))
    app = QApplication.instance() or QApplication([])
    configure_resident_qt_application(app)
    lifecycle_holder = {}
    presenter = UniversityPresenter(context, courses)
    document_presenter = DocumentPresenter(documents, DocumentImportService(documents, config.data_dir / "documents"))
    llm_service = LlmService(OllamaEngine())
    try:
        nova = NovaOverlayAdapter(NovaOverlayClient.from_environment())
    except Exception:
        logging.getLogger(__name__).warning("NOVA initialization failed; University AI continues")
        nova = NovaOverlayAdapter()
    tray = SystemTrayController(
        presenter,
        lambda: SettingsDialog(settings, startup),
        lambda: lifecycle_holder["lifecycle"].stop() or app.quit(),
        lambda: DocumentsDialog(document_presenter),
        lambda: AiQuestionDialog(llm_service, nova=nova),
    )
    capture_service = ScreenCaptureService(
        QtScreenCaptureBackend(), captures, CaptureStorageService(config.data_dir / "captures")
    )
    ocr_service = OcrService(ocr_results, documents, captures, TesseractOcrEngine())
    tray.set_capture_controller(ScreenCaptureController(
        capture_service,
        on_success=lambda body: tray.show_message("画面キャプチャ", body),
        on_failure=lambda body: tray.show_message("画面キャプチャ", body),
        ocr_service=ocr_service,
        on_ocr_result=lambda text: QMessageBox.information(None, "OCR結果", text),
        llm_service=llm_service,
        on_llm_result=lambda text: QMessageBox.information(None, "AI回答", text),
        nova=nova,
    ))
    adapter = FallbackOnErrorAdapter(
        WindowsToastAdapter(registration=toast_registration),
        TrayFallbackAdapter(tray.show_message),
    )
    service = NotificationService(events, adapter, nova=nova)
    scheduler = UniversityScheduler(context, rules, service)
    dispatcher = ApplicationCommandDispatcher(tray.command_handlers(), app)
    tray.set_command_dispatcher(dispatcher)
    nova.configure_commands(dispatcher)
    lifecycle = ApplicationLifecycle(nova, tray, scheduler, database, dispatcher)
    lifecycle_holder["lifecycle"] = lifecycle
    app.aboutToQuit.connect(lifecycle.stop)
    nova.start()
    nova.idle()
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
    lifecycle = None
    try:
        app, tray, scheduler, lifecycle = build_resident_application(config)
        if not tray.start():
            logging.getLogger(__name__).error("University AI cannot run without System Tray")
            return 1
        scheduler.start()
        result = app.exec()
        return result
    except Exception:
        logging.getLogger(__name__).exception("University AI resident startup failed")
        return 1
    finally:
        if lifecycle is not None:
            lifecycle.stop()


if __name__ == "__main__":
    raise SystemExit(main())
