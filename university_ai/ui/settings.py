from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox

from university_ai.app.config import SettingsStore, UserSettings


class SettingsDialog(QDialog):
    def __init__(self, store: SettingsStore, startup_adapter, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("University AI Settings")
        self._store = store
        self._startup = startup_adapter
        self._logger = logging.getLogger(__name__)
        settings = store.load()
        layout = QFormLayout(self)
        self.course = QCheckBox(); self.course.setChecked(settings.course_notifications)
        self.assignment = QCheckBox(); self.assignment.setChecked(settings.assignment_notifications)
        self.exam = QCheckBox(); self.exam.setChecked(settings.exam_notifications)
        self.startup = QCheckBox(); self.startup.setChecked(settings.startup_enabled)
        self.course_minutes = self._spin(settings.course_minutes)
        self.assignment_minutes = self._spin(settings.assignment_minutes)
        self.exam_minutes = self._spin(settings.exam_minutes)
        layout.addRow("授業通知", self.course); layout.addRow("課題通知", self.assignment); layout.addRow("試験通知", self.exam)
        layout.addRow("授業通知（分前）", self.course_minutes); layout.addRow("課題通知（分前）", self.assignment_minutes)
        layout.addRow("試験通知（分前）", self.exam_minutes); layout.addRow("ログオン時に起動", self.startup)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addRow(buttons)

    @staticmethod
    def _spin(value: int) -> QSpinBox:
        spin = QSpinBox(); spin.setRange(0, 7 * 24 * 60); spin.setValue(value); return spin

    def current_settings(self) -> UserSettings:
        return UserSettings(self.course.isChecked(), self.assignment.isChecked(), self.exam.isChecked(), self.course_minutes.value(),
                            self.assignment_minutes.value(), self.exam_minutes.value(), self.startup.isChecked())

    def save(self) -> None:
        settings = self.current_settings()
        self._store.save(settings)
        try:
            self._startup.enable() if settings.startup_enabled else self._startup.disable()
        except OSError:
            self._logger.exception("Startup setting could not be applied")
        self.accept()
