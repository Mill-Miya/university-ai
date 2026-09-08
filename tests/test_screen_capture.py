from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from university_ai.capture.backend import CaptureBackendError, CaptureRectangle, CapturedFrame
from university_ai.capture.service import CaptureStorageService, ScreenCaptureService
from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.models import CaptureType, ScreenCapture
from university_ai.database.repository import ScreenCaptureRepository
from university_ai.ui.capture import ScreenCaptureController
from university_ai.ui.tray import SystemTrayController


class FakeImage:
    def __init__(self, width=120, height=80, *, save_result=True):
        self._width, self._height, self._save_result = width, height, save_result

    def toImage(self): return self
    def width(self): return self._width
    def height(self): return self._height
    def save(self, path, image_format):
        assert image_format == "PNG"
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        return self._save_result


class FakeBackend:
    def __init__(self): self.calls = []
    def capture_full_screen(self):
        self.calls.append("full")
        return CapturedFrame(FakeImage(), CaptureType.FULL_SCREEN, 0, metadata_json=json.dumps({"source": "fake"}))
    def capture_active_window(self):
        self.calls.append("active")
        return CapturedFrame(FakeImage(100, 50), CaptureType.ACTIVE_WINDOW, 0, "Window", json.dumps({"hwnd": 12}))
    def capture_region(self, region):
        self.calls.append(region)
        return CapturedFrame(FakeImage(region.width, region.height), CaptureType.REGION, 0, metadata_json=json.dumps({"region": [region.x, region.y]}))


@pytest.fixture
def capture_services(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    connection = database.connect(); migrate(connection)
    repository = ScreenCaptureRepository(connection)
    backend = FakeBackend()
    service = ScreenCaptureService(backend, repository, CaptureStorageService(tmp_path / "captures"))
    yield repository, backend, service
    database.stop()


def test_full_active_and_region_capture_persist_png(capture_services):
    repository, backend, service = capture_services
    full = service.capture_full_screen().capture
    active = service.capture_active_window().capture
    region = service.capture_region(CaptureRectangle(10, 20, 30, 40)).capture

    assert backend.calls == ["full", "active", CaptureRectangle(10, 20, 30, 40)]
    assert [item.capture_type for item in repository.list()] == [CaptureType.REGION, CaptureType.ACTIVE_WINDOW, CaptureType.FULL_SCREEN]
    assert active.window_title == "Window" and region.width == 30 and region.height == 40
    assert Path(full.stored_path).suffix == ".png"
    assert Path(full.stored_path).read_bytes().startswith(b"\x89PNG")


def test_capture_storage_paths_are_unique_and_timezone_aware(tmp_path):
    storage = CaptureStorageService(tmp_path)
    now = datetime(2026, 9, 8, 3, tzinfo=UTC)
    first = storage.store_png(FakeImage(), now)
    second = storage.store_png(FakeImage(), now)
    assert first != second and first.parts[-3:-1] == ("2026", "09")
    with pytest.raises(ValueError, match="Timezone-aware"):
        storage.store_png(FakeImage(), datetime(2026, 9, 8, 3))


def test_invalid_region_backend_failure_and_db_failure_do_not_leave_successful_capture(capture_services, tmp_path):
    repository, backend, service = capture_services
    with pytest.raises(CaptureBackendError):
        service.capture_region(CaptureRectangle(0, 0, 0, 5))
    assert backend.calls == []

    class BrokenBackend:
        def capture_full_screen(self): raise CaptureBackendError("unavailable")
    with pytest.raises(CaptureBackendError):
        ScreenCaptureService(BrokenBackend(), repository, CaptureStorageService(tmp_path / "broken")).capture_full_screen()

    class BrokenRepository:
        def create(self, _capture): raise RuntimeError("database unavailable")
    storage_directory = tmp_path / "cleanup"
    with pytest.raises(RuntimeError):
        ScreenCaptureService(FakeBackend(), BrokenRepository(), CaptureStorageService(storage_directory)).capture_full_screen()
    assert not list(storage_directory.rglob("*.png"))


def test_capture_restart_persistence_and_cleanup_semantics(capture_services, tmp_path):
    repository, _backend, service = capture_services
    capture = service.capture_full_screen().capture
    path = Path(capture.stored_path)
    assert path.is_file()
    assert service.delete(capture.id or 0)
    assert not path.exists() and repository.get(capture.id or 0) is None

    direct = service.capture_full_screen().capture
    direct_path = Path(direct.stored_path)
    assert repository.delete_metadata(direct.id or 0)
    assert direct_path.exists()  # Repository deletes metadata only; service owns image cleanup.


def test_capture_is_available_after_database_restart(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    connection = database.connect(); migrate(connection)
    repository = ScreenCaptureRepository(connection)
    capture = ScreenCaptureService(FakeBackend(), repository, CaptureStorageService(tmp_path / "captures")).capture_full_screen().capture
    database.stop()

    reopened = Database(tmp_path / "app.sqlite3")
    reopened_connection = reopened.connect(); migrate(reopened_connection)
    assert ScreenCaptureRepository(reopened_connection).get(capture.id or 0) == capture
    reopened.stop()


def test_capture_repository_rejects_naive_datetime(capture_services):
    repository, _backend, _service = capture_services
    with pytest.raises(ValueError, match="Timezone-aware"):
        repository.create(ScreenCapture(None, CaptureType.FULL_SCREEN, "capture.png", 1, 1, datetime.now()))


def test_capture_controller_reports_success_failure_and_cancel():
    successes, failures = [], []

    class Service:
        def capture_full_screen(self): return type("Result", (), {"capture": type("Capture", (), {"stored_path": "ok.png"})()})()
        def capture_active_window(self): raise RuntimeError("no window")
        def capture_region(self, _region): raise AssertionError("cancel must not capture")
    class Overlay:
        def __init__(self, selected, cancelled): self.selected, self.cancelled = selected, cancelled; self.shown = False
        def show(self): self.shown = True
        def raise_(self): pass
        def activateWindow(self): pass

    holder = {}
    def factory(selected, cancelled):
        holder["overlay"] = Overlay(selected, cancelled); return holder["overlay"]
    controller = ScreenCaptureController(Service(), overlay_factory=factory, on_success=successes.append, on_failure=failures.append)
    controller.capture_full_screen(); controller.capture_active_window(); controller.select_region(); holder["overlay"].cancelled()
    assert successes == ["保存しました: ok.png"] and failures == ["画面キャプチャを保存できませんでした。"]


def test_tray_wires_capture_submenu_without_real_screen():
    class Style:
        def standardIcon(self, _): return "icon"
    class Application:
        def style(self): return Style()
    class Tray:
        def __init__(self, *_): self.visible = False
        def setContextMenu(self, menu): self.menu = menu
        def show(self): self.visible = True
        def isVisible(self): return self.visible
        def hide(self): self.visible = False
    class Menu:
        def __init__(self): self.actions, self.submenus = [], []
        def addAction(self, *action): self.actions.append(action)
        def addSeparator(self): self.actions.append(("separator",))
        def addMenu(self, title):
            child = Menu(); self.submenus.append((title, child)); return child
    class CaptureController:
        def capture_full_screen(self): pass
        def capture_active_window(self): pass
        def select_region(self): pass

    tray = SystemTrayController(None, lambda: None, lambda: None, system_tray_available=lambda: True,
                                application_provider=lambda: Application(), tray_factory=Tray, menu_factory=Menu)
    tray.set_capture_controller(CaptureController())
    assert tray.start()
    assert tray._capture_menu is not None and len(tray._capture_menu.actions) == 3
