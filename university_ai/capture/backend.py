from __future__ import annotations

import json
import os
from dataclasses import dataclass

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

from university_ai.database.models import CaptureType


class CaptureBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaptureRectangle:
    """Logical, primary-screen-local coordinates used by Qt's QScreen API."""

    x: int
    y: int
    width: int
    height: int

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise CaptureBackendError("capture region must have positive dimensions")


@dataclass(frozen=True)
class CapturedFrame:
    image: object
    capture_type: CaptureType
    monitor_index: int | None
    window_title: str | None = None
    metadata_json: str = "{}"


class QtScreenCaptureBackend:
    """Qt/Win32 adapter. It captures only when called by a user-facing action."""

    def capture_full_screen(self) -> CapturedFrame:
        screen = self._primary_screen()
        image = screen.grabWindow(0)
        self._validate_image(image)
        return CapturedFrame(
            image,
            CaptureType.FULL_SCREEN,
            self._screen_index(screen),
            metadata_json=json.dumps({"coordinate_space": "qt-logical-primary-screen"}),
        )

    def capture_active_window(self) -> CapturedFrame:
        if os.name != "nt":
            raise CaptureBackendError("active window capture is only available on Windows")
        try:
            import win32gui
        except ImportError as error:
            raise CaptureBackendError("Windows foreground-window API is unavailable") from error
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise CaptureBackendError("no foreground window is available")
        screen = self._primary_screen()
        image = screen.grabWindow(hwnd)
        self._validate_image(image)
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            title = win32gui.GetWindowText(hwnd) or None
        except Exception:
            left = top = right = bottom = 0
            title = None
        return CapturedFrame(
            image,
            CaptureType.ACTIVE_WINDOW,
            # GetWindowRect uses physical Windows pixels while Qt region
            # geometry uses logical coordinates under DPI scaling. Do not
            # report a guessed monitor for a foreground window yet.
            None,
            window_title=title,
            metadata_json=json.dumps({"hwnd": int(hwnd), "window_rect_physical": [left, top, right, bottom]}),
        )

    def capture_region(self, rectangle: CaptureRectangle) -> CapturedFrame:
        rectangle.validate()
        screen = self._primary_screen()
        geometry: QRect = screen.geometry()
        if rectangle.x < 0 or rectangle.y < 0 or rectangle.x + rectangle.width > geometry.width() or rectangle.y + rectangle.height > geometry.height():
            raise CaptureBackendError("capture region is outside the primary screen")
        image = screen.grabWindow(0, rectangle.x, rectangle.y, rectangle.width, rectangle.height)
        self._validate_image(image)
        return CapturedFrame(
            image,
            CaptureType.REGION,
            self._screen_index(screen),
            metadata_json=json.dumps({
                "coordinate_space": "qt-logical-primary-screen",
                "region": [rectangle.x, rectangle.y, rectangle.width, rectangle.height],
            }),
        )

    @staticmethod
    def _validate_image(image: object) -> None:
        if image is None or image.isNull():
            raise CaptureBackendError("screen capture returned an empty image")

    @staticmethod
    def _primary_screen():
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            raise CaptureBackendError("primary screen is unavailable")
        return screen

    @staticmethod
    def _screen_index(screen) -> int:
        screens = QGuiApplication.screens()
        return screens.index(screen) if screen in screens else 0
