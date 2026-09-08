import sys
from types import ModuleType

from university_ai.app import main as main_module
from university_ai.app.lifecycle import ApplicationLifecycle
from university_ai.core.rules import NotificationCandidate
from university_ai.notification.windows import WindowsToastAdapter


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
    WindowsToastAdapter(app_id="UniversityAI").send(candidate)
    assert ("app_id", "UniversityAI") in calls and any(item[0] == "show" for item in calls)
