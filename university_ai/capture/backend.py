from __future__ import annotations

import json
import os
from dataclasses import dataclass

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication, QWindow

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


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    title: str | None
    rectangle_physical: tuple[int, int, int, int]


class Win32WindowResolver:
    """Resolves a visible non-Shell window without treating the Tray as content."""

    _SHELL_CLASSES = {"Shell_TrayWnd", "NotifyIconOverflowWindow", "Progman", "WorkerW"}

    def __init__(self, *, api=None, current_pid: int | None = None) -> None:
        if api is None:
            if os.name != "nt":
                raise CaptureBackendError("active window capture is only available on Windows")
            try:
                import win32gui
                import win32process
            except ImportError as error:
                raise CaptureBackendError("Windows foreground-window API is unavailable") from error
            api = _PyWin32WindowApi(win32gui, win32process)
        self._api = api
        self._current_pid = current_pid if current_pid is not None else os.getpid()

    def snapshot_foreground(self) -> WindowTarget | None:
        return self._as_target(self._api.foreground_window())

    def resolve(self, preferred_hwnd: int | None = None) -> WindowTarget:
        preferred = self._as_target(preferred_hwnd) if preferred_hwnd else None
        if preferred is not None:
            return preferred
        target = self.snapshot_foreground()
        if target is None:
            raise CaptureBackendError("no valid external foreground window is available")
        return target

    def _as_target(self, hwnd: int | None) -> WindowTarget | None:
        if not hwnd or not self._api.is_window(hwnd) or not self._api.is_visible(hwnd) or self._api.is_iconic(hwnd):
            return None
        _thread_id, process_id = self._api.window_process_id(hwnd)
        window_class = self._api.class_name(hwnd)
        if process_id == self._current_pid or window_class in self._SHELL_CLASSES:
            return None
        rectangle = self._api.window_rect(hwnd)
        if rectangle[2] <= rectangle[0] or rectangle[3] <= rectangle[1]:
            return None
        return WindowTarget(hwnd, self._api.window_title(hwnd) or None, rectangle)


class _PyWin32WindowApi:
    def __init__(self, gui, process) -> None:
        self._gui = gui
        self._process = process

    def foreground_window(self): return self._gui.GetForegroundWindow()
    def is_window(self, hwnd): return self._gui.IsWindow(hwnd)
    def is_visible(self, hwnd): return self._gui.IsWindowVisible(hwnd)
    def is_iconic(self, hwnd): return self._gui.IsIconic(hwnd)
    def window_process_id(self, hwnd): return self._process.GetWindowThreadProcessId(hwnd)
    def class_name(self, hwnd): return self._gui.GetClassName(hwnd)
    def window_title(self, hwnd): return self._gui.GetWindowText(hwnd)
    def window_rect(self, hwnd): return self._gui.GetWindowRect(hwnd)


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

    def __init__(self, *, window_resolver: Win32WindowResolver | None = None) -> None:
        self._window_resolver = window_resolver

    def snapshot_active_window(self) -> int | None:
        target = self._resolver().snapshot_foreground()
        return target.hwnd if target is not None else None

    def capture_active_window(self, preferred_hwnd: int | None = None) -> CapturedFrame:
        target = self._resolver().resolve(preferred_hwnd)
        window = QWindow.fromWinId(target.hwnd)
        if window is None or window.geometry().isEmpty():
            raise CaptureBackendError("active window has no Qt capture geometry")
        screen = window.screen() or self._primary_screen()
        geometry = window.geometry()
        # Desktop-region capture reads the composed pixels after the Tray menu
        # closes. It avoids black frames from QScreen.grabWindow(HWND) for
        # GPU-composited applications such as Chromium.
        image = screen.grabWindow(
            0,
            geometry.x() - screen.geometry().x(),
            geometry.y() - screen.geometry().y(),
            geometry.width(),
            geometry.height(),
        )
        self._validate_image(image)
        return CapturedFrame(
            image,
            CaptureType.ACTIVE_WINDOW,
            self._screen_index(screen),
            window_title=target.title,
            metadata_json=json.dumps({
                "hwnd": target.hwnd,
                "window_rect_physical": target.rectangle_physical,
                "window_rect_logical": [geometry.x(), geometry.y(), geometry.width(), geometry.height()],
                "capture_method": "desktop-region",
            }),
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

    def _resolver(self) -> Win32WindowResolver:
        if self._window_resolver is None:
            self._window_resolver = Win32WindowResolver()
        return self._window_resolver

    @staticmethod
    def _screen_index(screen) -> int:
        screens = QGuiApplication.screens()
        return screens.index(screen) if screen in screens else 0
