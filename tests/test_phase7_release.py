import sys
from types import ModuleType

from university_ai.app import main as main_module
from university_ai.app.lifecycle import ApplicationLifecycle
from university_ai.core.rules import NotificationCandidate
from university_ai.notification.windows import WindowsToastAdapter
from university_ai.notification.registration import APP_USER_MODEL_ID, WindowsToastRegistration
from university_ai.ui.tray import SystemTrayController


def test_lifecycle_stops_in_reverse_order_and_continues_after_failure():
    calls = []

    class Component:
        def __init__(self, name, fail=False): self.name, self.fail = name, fail
        def stop(self):
            calls.append(self.name)
            if self.fail: raise RuntimeError("stop failure")

    ApplicationLifecycle(Component("database"), Component("scheduler", True), Component("tray")).stop()
    assert calls == ["tray", "scheduler", "database"]


def test_resident_qt_application_does_not_quit_when_last_dialog_closes():
    class FakeApplication:
        def __init__(self): self.quit_on_last_window_closed = None
        def setQuitOnLastWindowClosed(self, value): self.quit_on_last_window_closed = value

    application = FakeApplication()
    main_module.configure_resident_qt_application(application)
    assert application.quit_on_last_window_closed is False


def test_tray_retains_context_menu_for_resident_lifetime():
    class Style:
        def standardIcon(self, _): return "icon"
    class Application:
        def style(self): return Style()
    class Tray:
        def __init__(self, icon, parent): self.menu = None; self.visible = False
        def setContextMenu(self, menu): self.menu = menu
        def show(self): self.visible = True
        def isVisible(self): return self.visible
        def hide(self): self.visible = False
    class Menu:
        def __init__(self): self.actions = []
        def addAction(self, *args): self.actions.append(args)
        def addSeparator(self): self.actions.append(("separator",))

    controller = SystemTrayController(
        None, lambda: None, lambda: None, system_tray_available=lambda: True,
        application_provider=lambda: Application(), tray_factory=Tray, menu_factory=Menu,
    )
    assert controller.start()
    assert controller._menu is controller._tray.menu
    assert len(controller._menu.actions) == 7
    controller.stop()
    assert controller._menu is None and controller._tray is None


def test_main_releases_lifecycle_when_tray_is_unavailable(monkeypatch, tmp_path):
    stopped = []

    class Tray:
        def start(self): return False

    class Lifecycle:
        def stop(self): stopped.append(True)

    monkeypatch.setattr(main_module, "build_resident_application", lambda config: (None, Tray(), None, Lifecycle()))
    assert main_module.main(tmp_path, run_event_loop=True) == 1
    assert stopped == [True]


def test_windows_toast_uses_winrt_identifier_factory(monkeypatch):
    calls = []

    class Document:
        def load_xml(self, value): calls.append(("xml", value))

    class XmlDocument:
        def load_xml(self, value): calls.append(("xml", value))

    class ToastNotification:
        def __init__(self, document): calls.append(("notification", document))

    class Notifier:
        class Setting:
            name = "ENABLED"
        setting = Setting()
        def show(self, notification): calls.append(("show", notification))

    class Manager:
        @staticmethod
        def create_toast_notifier_with_id(app_id):
            calls.append(("app_id", app_id)); return Notifier()

    dom = ModuleType("winrt.windows.data.xml.dom"); dom.XmlDocument = XmlDocument
    notifications = ModuleType("winrt.windows.ui.notifications")
    notifications.ToastNotification = ToastNotification; notifications.ToastNotificationManager = Manager
    monkeypatch.setitem(sys.modules, "winrt.windows.data.xml.dom", dom)
    monkeypatch.setitem(sys.modules, "winrt.windows.ui.notifications", notifications)
    candidate = NotificationCandidate("x", "x", 1, __import__("datetime").datetime.now(__import__("datetime").UTC), "<Title>", "Body")
    class Registration:
        def register(self): return True

    WindowsToastAdapter(app_id=APP_USER_MODEL_ID, registration=Registration()).send(candidate)
    assert ("app_id", APP_USER_MODEL_ID) in calls and any(item[0] == "show" for item in calls)


def test_windows_toast_registration_creates_one_stable_shortcut(tmp_path):
    writes = []
    applied = []

    def write_shortcut(path, app_id, executable, project_root, arguments):
        writes.append((path, app_id, executable, project_root, arguments))
        path.touch()

    registration = WindowsToastRegistration(
        shortcut_directory=tmp_path,
        project_root=tmp_path,
        executable=tmp_path / "python.exe",
        shortcut_writer=write_shortcut,
        process_identity_setter=applied.append,
    )
    assert registration.register()
    assert registration.register()
    assert registration.shortcut_path == tmp_path / "University AI.lnk"
    assert registration.registered()
    assert writes == [(tmp_path / "University AI.lnk", APP_USER_MODEL_ID, tmp_path / "python.exe", tmp_path, "-m university_ai.app.main")]
    if sys.platform == "win32":
        assert registration.apply_to_current_process()
        assert applied == [APP_USER_MODEL_ID]
    else:
        assert not registration.apply_to_current_process()
        assert applied == []
    assert registration.unregister()
    assert registration.unregister()


def test_windows_toast_rejects_blocked_notifier_setting(monkeypatch):
    class XmlDocument:
        def load_xml(self, _value): pass

    class ToastNotification:
        def __init__(self, _document): pass

    class Notifier:
        class Setting:
            name = "DISABLED_FOR_USER"
        setting = Setting()
        def show(self, _notification): raise AssertionError("blocked notifier must not show")

    class Manager:
        @staticmethod
        def create_toast_notifier_with_id(_app_id): return Notifier()

    dom = ModuleType("winrt.windows.data.xml.dom"); dom.XmlDocument = XmlDocument
    notifications = ModuleType("winrt.windows.ui.notifications")
    notifications.ToastNotification = ToastNotification; notifications.ToastNotificationManager = Manager
    monkeypatch.setitem(sys.modules, "winrt.windows.data.xml.dom", dom)
    monkeypatch.setitem(sys.modules, "winrt.windows.ui.notifications", notifications)

    class Registration:
        def register(self): return True

    candidate = NotificationCandidate("x", "x", 1, __import__("datetime").datetime.now(__import__("datetime").UTC), "Title", "Body")
    import pytest
    with pytest.raises(RuntimeError, match="DISABLED_FOR_USER"):
        WindowsToastAdapter(registration=Registration()).send(candidate)


def test_windows_toast_sends_when_setting_diagnostic_is_unavailable(monkeypatch):
    calls = []

    class XmlDocument:
        def load_xml(self, _value): pass

    class ToastNotification:
        def __init__(self, _document): pass

    class Notifier:
        @property
        def setting(self): raise OSError("ERROR_NOT_FOUND")
        def show(self, _notification): calls.append("show")

    class Manager:
        @staticmethod
        def create_toast_notifier_with_id(_app_id): return Notifier()

    dom = ModuleType("winrt.windows.data.xml.dom"); dom.XmlDocument = XmlDocument
    notifications = ModuleType("winrt.windows.ui.notifications")
    notifications.ToastNotification = ToastNotification; notifications.ToastNotificationManager = Manager
    monkeypatch.setitem(sys.modules, "winrt.windows.data.xml.dom", dom)
    monkeypatch.setitem(sys.modules, "winrt.windows.ui.notifications", notifications)

    class Registration:
        def register(self): return True

    candidate = NotificationCandidate("x", "x", 1, __import__("datetime").datetime.now(__import__("datetime").UTC), "Title", "Body")
    WindowsToastAdapter(registration=Registration()).send(candidate)
    assert calls == ["show"]
