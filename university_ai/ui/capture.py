from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from university_ai.capture.backend import CaptureRectangle
from university_ai.ui.llm import LlmWorker
from university_ai.overlay import NovaOverlayAdapter


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
        ocr_service=None,
        on_ocr_result: Callable[[str], None] | None = None,
        llm_service=None,
        on_llm_result: Callable[[str], None] | None = None,
        defer: Callable[[Callable[[], None]], None] | None = None,
        nova=None,
    ) -> None:
        self._service = service
        self._overlay_factory = overlay_factory
        self._on_success = on_success or (lambda _message: None)
        self._on_failure = on_failure or (lambda _message: None)
        self._ocr_service = ocr_service
        self._on_ocr_result = on_ocr_result or (lambda _text: None)
        self._llm_service = llm_service; self._on_llm_result = on_llm_result or (lambda _text: None); self._llm_worker=None
        self._overlay = None
        self._active_window_hint: int | None = None
        self._defer = defer or (lambda callback: QTimer.singleShot(self._ACTIVE_CAPTURE_SETTLE_MS, callback))
        self._logger = logging.getLogger(__name__)
        self._nova = NovaOverlayAdapter(nova)
        self._selection_token = None
        self._llm_workers = set()

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
        self._start_selection(self._capture_region)

    def select_region_and_ocr(self) -> None:
        if self._ocr_service is None:
            self._nova.error()
            self._notify(self._on_failure, "OCRは利用できません。")
            return
        self._start_selection(self._capture_region_and_ocr)

    def select_region_and_ask(self) -> None:
        if self._ocr_service is None or self._llm_service is None:
            self._nova.error()
            self._notify(self._on_failure, "OCRまたはローカルAIは利用できません。")
            return
        self._start_selection(self._capture_region_and_ask)

    def _start_selection(self, selected: Callable[[CaptureRectangle], None]) -> None:
        if self._overlay is not None:
            return
        self._selection_token = self._nova.begin('scanning')
        try:
            self._overlay = self._overlay_factory(selected, self._cancelled)
            self._overlay.show()
            self._overlay.raise_()
            self._overlay.activateWindow()
        except Exception:
            self._overlay = None
            self._nova.finish(self._take_selection_token(), 'error')
            self._logger.exception("Region-selection overlay could not start")
            self._notify(self._on_failure, "範囲選択を開始できませんでした。")

    def _capture_region(self, rectangle: CaptureRectangle) -> None:
        self._overlay = None
        self._run(lambda: self._service.capture_region(rectangle), token=self._take_selection_token())

    def _capture_region_and_ocr(self, rectangle: CaptureRectangle) -> None:
        self._overlay = None
        token = self._take_selection_token() or self._nova.begin('scanning')
        try:
            captured = self._service.capture_region(rectangle).capture
            assert self._ocr_service is not None
            outcome = self._ocr_service.recognize_capture(captured.id or 0)
            if outcome.result.status.value != "EXTRACTED":
                raise RuntimeError(outcome.result.error or "OCR failed")
        except Exception:
            self._nova.finish(token, 'error')
            self._logger.exception("Region OCR failed")
            self._notify(self._on_failure, "範囲内の文字を読み取れませんでした。")
            return
        self._nova.finish(token, 'notification')
        self._notify(self._on_success, f"保存しました: {captured.stored_path}")
        self._notify(self._on_ocr_result, outcome.result.text or "文字を検出できませんでした。")

    def _capture_region_and_ask(self, rectangle: CaptureRectangle) -> None:
        self._overlay = None
        token = self._take_selection_token() or self._nova.begin('scanning')
        try:
            captured = self._service.capture_region(rectangle).capture
            outcome = self._ocr_service.recognize_capture(captured.id or 0)
            text = outcome.result.text or ""
            if outcome.result.status.value != "EXTRACTED" or not text.strip(): raise RuntimeError("OCR failed or empty")
        except Exception:
            self._nova.finish(token, 'error')
            self._logger.exception("Region OCR to LLM failed"); self._notify(self._on_failure, "範囲内の文字を読み取れませんでした。"); return
        self._nova.finish(token, 'notification')
        self._notify(self._on_success, f"保存しました: {captured.stored_path}")
        try:
            worker=LlmWorker(action=lambda: self._llm_service.explain_text(text), nova=self._nova)
            self._llm_worker=worker
            self._llm_workers.add(worker)
            worker.completed.connect(lambda answer: self._notify(self._on_llm_result, answer))
            worker.failed.connect(lambda _error: self._notify(self._on_failure, "ローカルAIの回答を生成できませんでした。"))
            worker.finished.connect(lambda: self._release_worker(worker))
            worker.start()
        except Exception:
            self._nova.error()
            self._logger.exception("Capture LLM worker could not start")
            self._notify(self._on_failure, "ローカルAIの回答を生成できませんでした。")

    def _release_worker(self, worker):
        self._llm_workers.discard(worker)
        if self._llm_worker is worker:
            self._llm_worker = None

    def _take_selection_token(self):
        token, self._selection_token = self._selection_token, None
        return token

    def _cancelled(self) -> None:
        self._overlay = None
        self._nova.finish(self._take_selection_token())

    def _run(self, action: Callable[[], object], *, token=None) -> None:
        token = token or self._nova.begin('scanning')
        try:
            result = action()
        except Exception:
            self._nova.finish(token, 'error')
            self._logger.exception("Screen capture failed")
            self._notify(self._on_failure, "画面キャプチャを保存できませんでした。")
            return
        self._nova.finish(token, 'notification')
        self._notify(self._on_success, f"保存しました: {result.capture.stored_path}")

    def _notify(self, callback: Callable[[str], None], message: str) -> None:
        try:
            callback(message)
        except Exception:
            self._logger.exception("Screen capture UI notification failed")
