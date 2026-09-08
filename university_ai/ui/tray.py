from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from university_ai.ui.presenter import UniversityPresenter


class SystemTrayController:
    def __init__(
        self, presenter: UniversityPresenter, settings_factory, on_quit,
        *, system_tray_available: Callable[[], bool] = QSystemTrayIcon.isSystemTrayAvailable,
    ) -> None:
        self._presenter = presenter
        self._settings_factory = settings_factory
        self._on_quit = on_quit
        self._logger = logging.getLogger(__name__)
        self._tray: QSystemTrayIcon | None = None
        self._system_tray_available = system_tray_available

    @property
    def available(self) -> bool:
        return self._system_tray_available()

    def start(self) -> bool:
        if not self.available:
            self._logger.warning("System Tray is unavailable")
            return False
        app = QApplication.instance()
        assert app is not None
        self._tray = QSystemTrayIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), app)
        menu = QMenu()
        menu.addAction("状態: 実行中")
        menu.addAction("今日の予定", lambda: self._show("今日の予定", self._presenter.today_courses()))
        menu.addAction("課題", lambda: self._show("未完了課題", self._presenter.assignments()))
        menu.addAction("試験", lambda: self._show("試験", self._presenter.exams()))
        menu.addAction("設定", self._open_settings)
        menu.addSeparator()
        menu.addAction("終了", self._on_quit)
        self._tray.setContextMenu(menu); self._tray.show()
        return True

    def show_message(self, title: str, body: str) -> None:
        if self._tray is None or not self._tray.isVisible():
            raise RuntimeError("Tray notification is unavailable")
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information)

    def stop(self) -> None:
        if self._tray is not None:
            self._tray.hide()

    def _show(self, title: str, lines: list[str]) -> None:
        QMessageBox.information(None, title, "\n".join(lines) if lines else "該当する項目はありません。")

    def _open_settings(self) -> None:
        self._settings_factory().exec()
