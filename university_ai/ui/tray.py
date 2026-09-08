from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from university_ai.ui.presenter import UniversityPresenter


class SystemTrayController:
    def __init__(
        self, presenter: UniversityPresenter, settings_factory, on_quit,
        documents_factory: Callable[[], object] | None = None,
        llm_factory: Callable[[], object] | None = None,
        *, system_tray_available: Callable[[], bool] = QSystemTrayIcon.isSystemTrayAvailable,
        application_provider: Callable[[], QApplication | None] = QApplication.instance,
        tray_factory=QSystemTrayIcon,
        menu_factory=QMenu,
    ) -> None:
        self._presenter = presenter
        self._settings_factory = settings_factory
        self._on_quit = on_quit
        self._documents_factory = documents_factory
        self._llm_factory = llm_factory
        self._logger = logging.getLogger(__name__)
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._capture_menu: QMenu | None = None
        self._capture_controller = None
        self._system_tray_available = system_tray_available
        self._application_provider = application_provider
        self._tray_factory = tray_factory
        self._menu_factory = menu_factory

    @property
    def available(self) -> bool:
        return self._system_tray_available()

    def start(self) -> bool:
        self._logger.info("System Tray availability: %s", self.available)
        if not self.available:
            self._logger.warning("System Tray is unavailable")
            return False
        app = self._application_provider()
        assert app is not None
        self._tray = self._tray_factory(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), app)
        self._logger.info("System Tray object created")
        # QSystemTrayIcon is a QObject, not a QWidget, and therefore cannot
        # parent QMenu. Keep the Python reference for the resident lifetime.
        self._menu = self._menu_factory()
        self._menu.addAction("状態: 実行中")
        self._menu.addAction("今日の予定", lambda: self._show("今日の予定", self._presenter.today_courses()))
        self._menu.addAction("課題", lambda: self._show("未完了課題", self._presenter.assignments()))
        self._menu.addAction("試験", lambda: self._show("試験", self._presenter.exams()))
        if self._documents_factory is not None:
            self._menu.addAction("資料", self._open_documents)
        if self._llm_factory is not None:
            self._menu.addAction("AIに質問", self._open_llm)
        if self._capture_controller is not None:
            self._capture_menu = self._menu.addMenu("画面キャプチャ")
            about_to_show = getattr(self._capture_menu, "aboutToShow", None)
            if about_to_show is not None:
                about_to_show.connect(self._capture_controller.prepare_active_window_target)
            self._capture_menu.addAction("全画面", self._capture_controller.capture_full_screen)
            self._capture_menu.addAction("アクティブウィンドウ", self._capture_controller.capture_active_window)
            self._capture_menu.addAction("範囲選択", self._capture_controller.select_region)
            self._capture_menu.addAction("範囲を読取", self._capture_controller.select_region_and_ocr)
        self._menu.addAction("設定", self._open_settings)
        self._menu.addSeparator()
        self._menu.addAction("終了", self._on_quit)
        self._logger.info("System Tray context menu created")
        self._tray.setContextMenu(self._menu)
        self._tray.show()
        self._logger.info("System Tray show called; visible=%s", self._tray.isVisible())
        return True

    def show_message(self, title: str, body: str) -> None:
        if self._tray is None or not self._tray.isVisible():
            raise RuntimeError("Tray notification is unavailable")
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information)

    def stop(self) -> None:
        if self._tray is not None:
            self._tray.hide()
        self._menu = None
        self._capture_menu = None
        self._tray = None

    def set_capture_controller(self, controller) -> None:
        """Must be called before start so the tray can build the explicit capture menu."""
        if self._menu is not None:
            raise RuntimeError("capture controller must be configured before tray start")
        self._capture_controller = controller

    def _show(self, title: str, lines: list[str]) -> None:
        QMessageBox.information(None, title, "\n".join(lines) if lines else "該当する項目はありません。")

    def _open_settings(self) -> None:
        self._settings_factory().exec()

    def _open_documents(self) -> None:
        assert self._documents_factory is not None
        self._documents_factory().exec()

    def _open_llm(self) -> None:
        assert self._llm_factory is not None
        self._llm_factory().exec()
