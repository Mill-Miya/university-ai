from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from university_ai.capture.backend import CaptureRectangle


class CaptureSelectionOverlay(QWidget):
    """Replaceable plain selection UI, using Qt logical coordinates on primary screen."""

    def __init__(self, on_selected: Callable[[CaptureRectangle], None], on_cancelled: Callable[[], None]) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._start: QPoint | None = None
        self._current: QPoint | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("primary screen is unavailable")
        self.setGeometry(screen.geometry())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._current = self._start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        end = event.position().toPoint()
        rectangle = QRect(self._start, end).normalized()
        self._start = None
        self._current = None
        if rectangle.width() <= 0 or rectangle.height() <= 0:
            self._cancel()
            return
        selection = CaptureRectangle(rectangle.x(), rectangle.y(), rectangle.width(), rectangle.height())
        self.hide()
        QTimer.singleShot(0, lambda: self._on_selected(selection))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self._start is not None and self._current is not None:
            selected = QRect(self._start, self._current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selected, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(80, 170, 255), 2))
            painter.drawRect(selected)

    def _cancel(self) -> None:
        self.hide()
        self._on_cancelled()


class ScreenCaptureController:
    """UI coordinator. Backend and storage are only reached from explicit actions."""

    _ACTIVE_CAPTURE_SETTLE_MS = 500

    def __init__(
        self,
        service,
        *,
        overlay_factory: Callable[[Callable[[CaptureRectangle], None], Callable[[], None]], object] = CaptureSelectionOverlay,
        on_success: Callable[[str], None] | None = None,
        on_failure: Callable[[str], None] | None = None,
        defer: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._service = service
        self._overlay_factory = overlay_factory
        self._on_success = on_success or (lambda _message: None)
        self._on_failure = on_failure or (lambda _message: None)
        self._overlay = None
        self._active_window_hint: int | None = None
        self._defer = defer or (lambda callback: QTimer.singleShot(self._ACTIVE_CAPTURE_SETTLE_MS, callback))
        self._logger = logging.getLogger(__name__)

    def capture_full_screen(self) -> None:
        self._run(self._service.capture_full_screen)

    def capture_active_window(self) -> None:
        hint, self._active_window_hint = self._active_window_hint, None
        # QAction is emitted while the Tray menu owns focus. The bounded settle
        # wait lets Windows repaint the remembered external window; it is not
        # the target-selection mechanism. The backend revalidates that HWND.
        self._defer(lambda: self._run(lambda: self._service.capture_active_window(hint)))

    def prepare_active_window_target(self) -> None:
        """Remember the last valid external window while the capture menu opens."""
        try:
            self._active_window_hint = self._service.snapshot_active_window()
        except Exception:
            self._active_window_hint = None
            self._logger.warning("No valid active-window capture target was available")

    def select_region(self) -> None:
        if self._overlay is not None:
            return
        try:
            self._overlay = self._overlay_factory(self._capture_region, self._cancelled)
            self._overlay.show()
            self._overlay.raise_()
            self._overlay.activateWindow()
        except Exception:
            self._overlay = None
            self._logger.exception("Region-selection overlay could not start")
            self._notify(self._on_failure, "範囲選択を開始できませんでした。")

    def _capture_region(self, rectangle: CaptureRectangle) -> None:
        self._overlay = None
        self._run(lambda: self._service.capture_region(rectangle))

    def _cancelled(self) -> None:
        self._overlay = None

    def _run(self, action: Callable[[], object]) -> None:
        try:
            result = action()
        except Exception:
            self._logger.exception("Screen capture failed")
            self._notify(self._on_failure, "画面キャプチャを保存できませんでした。")
            return
        self._notify(self._on_success, f"保存しました: {result.capture.stored_path}")

    def _notify(self, callback: Callable[[str], None], message: str) -> None:
        try:
            callback(message)
        except Exception:
            self._logger.exception("Screen capture UI notification failed")
