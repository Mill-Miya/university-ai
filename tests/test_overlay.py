import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace as NS

import pytest

from university_ai.overlay import NovaOverlayAdapter, NovaOverlayClient
from university_ai.ui.capture import ScreenCaptureController
from university_ai.ui.llm import LlmWorker


class RecordingClient(NovaOverlayClient):
    def __init__(self):
        self.now = 0.0
        super().__init__(Path('unused'), clock=lambda: self.now)
        self.calls = []

    def begin(self, state):
        self.calls.append(('begin', state))
        return super().begin(state)

    def finish(self, token, outcome=None):
        self.calls.append(('finish', outcome))
        super().finish(token, outcome)


def test_priorities_tokens_expiration_and_idle_do_not_cancel_other_work():
    nova = RecordingClient()
    a, b = nova.begin('thinking'), nova.begin('thinking')
    nova.notification('not transmitted')
    assert nova.current_state() == 'thinking'
    scan = nova.begin('scanning')
    assert nova.current_state() == 'scanning'
    nova.error(); assert nova.current_state() == 'error'
    nova.now = 4; assert nova.current_state() == 'scanning'
    nova.finish(scan); nova.finish(a); nova.idle()
    assert nova.current_state() == 'thinking'
    nova.finish(b, 'notification'); assert nova.current_state() == 'notification'
    nova.now = 7; assert nova.current_state() == 'idle'
    assert nova.begin('full') is None
    nova.set_state('invalid'); assert nova.current_state() == 'idle'


@pytest.mark.parametrize('fails', [False, True])
def test_llm_success_error_preserve_result_and_return_idle(fails):
    nova = RecordingClient()
    def action():
        assert nova.current_state() == 'thinking'
        if fails: raise RuntimeError('engine down')
        return NS(text='answer stays in existing UI')
    worker = LlmWorker(action=action, nova=nova)
    replies, errors = [], []
    worker.completed.connect(replies.append); worker.failed.connect(errors.append)
    worker.run()
    assert nova.current_state() == ('error' if fails else 'notification')
    assert bool(errors) == fails and bool(replies) != fails
    assert nova.calls == [('begin', 'thinking'), ('finish', 'error' if fails else 'notification')]
    nova.now = 4; assert nova.current_state() == 'idle'


class Capture:
    def __init__(self, nova, fails=False): self.nova, self.fails = nova, fails
    def capture_full_screen(self):
        assert self.nova.current_state() == 'scanning'
        if self.fails: raise RuntimeError('capture failed')
        return NS(capture=NS(id=1, stored_path='capture.png'))
    def capture_region(self, _): return self.capture_full_screen()


@pytest.mark.parametrize('fails', [False, True])
def test_capture_success_error(fails):
    nova = RecordingClient(); success, failure = [], []
    controller = ScreenCaptureController(Capture(nova, fails), nova=nova, on_success=success.append, on_failure=failure.append)
    controller.capture_full_screen()
    assert bool(failure) == fails and bool(success) != fails
    assert nova.current_state() == ('error' if fails else 'notification')
    nova.now = 4; assert nova.current_state() == 'idle'


@pytest.mark.parametrize('fails', [False, True])
def test_ocr_stays_scanning_and_completes(fails):
    nova = RecordingClient(); results = []
    class Ocr:
        def recognize_capture(self, _):
            assert nova.current_state() == 'scanning'
            return NS(result=NS(status=NS(value='FAILED' if fails else 'EXTRACTED'), text='OCR text', error='failed'))
    controller = ScreenCaptureController(Capture(nova), nova=nova, ocr_service=Ocr(), on_ocr_result=results.append)
    controller._capture_region_and_ocr(None)
    assert bool(results) != fails
    assert nova.current_state() == ('error' if fails else 'notification')


def test_ocr_to_llm_releases_scanning_before_thinking(monkeypatch):
    nova = RecordingClient(); answers = []
    class SynchronousWorker(LlmWorker):
        def start(self): self.run(); self.finished.emit()
    monkeypatch.setattr('university_ai.ui.capture.LlmWorker', SynchronousWorker)
    class Llm:
        def explain_text(self, text):
            assert text == 'recognized'
            assert nova.current_state() == 'thinking'
            return NS(text='explanation')
    ocr = NS(recognize_capture=lambda _: NS(result=NS(status=NS(value='EXTRACTED'), text='recognized')))
    controller = ScreenCaptureController(Capture(nova), nova=nova, ocr_service=ocr, llm_service=Llm(), on_llm_result=answers.append)
    controller._capture_region_and_ask(None)
    assert answers == ['explanation']
    assert nova.calls == [('begin','scanning'),('finish','notification'),('begin','thinking'),('finish','notification')]
    assert not controller._llm_workers


def test_selection_cancellation_and_factory_failure_release_token():
    nova = RecordingClient()
    class Selection:
        def __init__(self, selected, cancelled): self.cancel = cancelled
        def show(self): pass
        def raise_(self): pass
        def activateWindow(self): pass
    controller = ScreenCaptureController(None, nova=nova, overlay_factory=Selection)
    controller.select_region(); assert nova.current_state() == 'scanning'
    controller._overlay.cancel(); assert nova.current_state() == 'idle'
    controller._overlay_factory = lambda *_: (_ for _ in ()).throw(RuntimeError('no display'))
    controller.select_region(); assert nova.current_state() == 'error'
    nova.now = 4; assert nova.current_state() == 'idle'


def test_broken_overlay_never_breaks_llm_capture_or_lifecycle():
    class Broken:
        def __getattr__(self, _): raise RuntimeError('overlay is broken')
    nova = NovaOverlayAdapter(Broken())
    nova.start(); nova.idle(); nova.notification(); nova.error(); nova.stop()
    replies = []
    worker = LlmWorker(action=lambda: NS(text='ok'), nova=nova)
    worker.completed.connect(replies.append); worker.run(); assert replies == ['ok']
    results = []
    service = NS(capture_full_screen=lambda: NS(capture=NS(stored_path='ok.png')))
    ScreenCaptureController(service, nova=nova, on_success=results.append).capture_full_screen()
    assert len(results) == 1


class Endpoint:
    """Real loopback peer for fail-open/reconnect tests; never launches a UI."""
    def __init__(self, file, token='a' * 64):
        self.file, self.token, self.packets, self.clients = file, token, [], []
        self.stopped = threading.Event()
        self.server = socket.socket(); self.server.bind(('127.0.0.1', 0)); self.server.listen()
        self.server.settimeout(.1)
        file.write_text(json.dumps({'v':1, 'port':self.server.getsockname()[1], 'token':token}), encoding='utf-8')
        self.thread = threading.Thread(target=self.run, daemon=True); self.thread.start()
    def run(self):
        while not self.stopped.is_set():
            try: client, _ = self.server.accept()
            except socket.timeout: continue
            except OSError: return
            self.clients.append(client); client.settimeout(.1); buffer = b''
            try:
                while not self.stopped.is_set():
                    try: data = client.recv(4096)
                    except socket.timeout: continue
                    if not data: break
                    buffer += data
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        packet = json.loads(line); self.packets.append(packet)
                        client.sendall(b'{"v":1,"ok":true}\n')
            except OSError: pass
            finally: client.close()
    def close(self):
        self.stopped.set(); self.server.close()
        for client in self.clients:
            try: client.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            client.close()
        self.thread.join(1)


def eventually(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, 'event did not occur'
        time.sleep(.02)


def test_connection_failure_reconnect_latest_state_shutdown_independent(tmp_path):
    file = tmp_path / 'endpoint.json'
    nova = NovaOverlayClient(file)
    started = time.monotonic(); nova.start(); token = nova.begin('thinking')
    assert time.monotonic() - started < .2
    first = Endpoint(file)
    try:
        eventually(lambda: any(p.get('state') == 'thinking' for p in first.packets))
        first.close()
        second = Endpoint(file, 'b' * 64)
        try:
            eventually(lambda: any(p.get('state') == 'thinking' for p in second.packets))
            nova.finish(token)
            eventually(lambda: any(p.get('state') == 'idle' for p in second.packets))
            nova.stop(); nova.stop()
            assert not nova._thread.is_alive()
            assert second.packets[-1]['op'] == 'shutdown' and second.packets[-1]['owner'] is None
            assert all(p['token'] == 'b' * 64 for p in second.packets)
            assert all('message' not in p for p in second.packets)
        finally: second.close()
    finally: nova.stop(); first.close()


def test_launch_is_shell_free_owned_once_and_cleanup_bounded(monkeypatch, tmp_path):
    from university_ai.overlay import client as module
    processes = []
    class Process:
        def __init__(self, argv, **kwargs): self.argv, self.kwargs, self.waited = argv, kwargs, False; processes.append(self)
        def wait(self, timeout): self.waited = True
    monkeypatch.setattr(module.subprocess, 'Popen', Process)
    nova = NovaOverlayClient(tmp_path / 'absent.json', command=['electron.exe', 'overlay'])
    nova.start(); eventually(lambda: bool(processes)); nova.stop()
    assert len(processes) == 1 and processes[0].waited
    assert processes[0].kwargs['env']['NOVA_OVERLAY_OWNER_TOKEN'] == nova._owner
    assert 'shell' not in processes[0].kwargs


def test_malformed_configuration_and_launch_failure_are_fail_open(monkeypatch, tmp_path):
    monkeypatch.setenv('NOVA_OVERLAY_COMMAND', '{broken')
    assert NovaOverlayClient.from_environment().command is None
    nova = NovaOverlayClient(tmp_path / 'absent.json', command=['not-a-real-executable-123'])
    nova.start(); time.sleep(.2); nova.stop()
    assert not nova._thread.is_alive()


def test_notification_delivery_preserved_and_duplicates_do_not_pulse(tmp_path):
    from datetime import UTC, datetime
    from university_ai.core.rules import NotificationCandidate
    from university_ai.database.database import Database
    from university_ai.database.migrations import migrate
    from university_ai.database.repository import NotificationEventRepository
    from university_ai.notification.service import NotificationService
    db = Database(tmp_path / 'app.sqlite3'); connection = db.connect(); migrate(connection)
    nova = RecordingClient(); delivered = []
    service = NotificationService(NotificationEventRepository(connection), NS(send=delivered.append), nova=nova)
    candidate = NotificationCandidate('test','course',1,datetime.now(UTC),'title','body')
    try:
        service.process([candidate]); assert len(delivered) == 1 and nova.current_state() == 'notification'
        nova.now = 4
        service.process([candidate]); assert len(delivered) == 1 and nova.current_state() == 'idle'
    finally: db.stop()


def test_composition_and_lifecycle_start_stop_overlay_once(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication
    from university_ai.app import main as module
    from university_ai.app.config import AppConfig
    app = QApplication.instance() or QApplication([])
    calls = []
    class Client:
        def start(self): calls.append('start')
        def set_state(self, state): calls.append(state)
        def stop(self): calls.append('stop')
    monkeypatch.setattr(module.NovaOverlayClient, 'from_environment', lambda: Client())
    monkeypatch.setattr(module, 'WindowsToastRegistration', lambda **_: NS(register=lambda: False))
    _, _, _, lifecycle = module.build_resident_application(AppConfig.default(tmp_path))
    lifecycle.stop(); lifecycle.stop()
    assert calls == ['start','idle','stop']
    app.aboutToQuit.disconnect(lifecycle.stop)


def test_composition_survives_overlay_constructor_failure(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication
    from university_ai.app import main as module
    from university_ai.app.config import AppConfig
    app = QApplication.instance() or QApplication([])
    def broken(): raise OSError('overlay config unavailable')
    monkeypatch.setattr(module.NovaOverlayClient, 'from_environment', broken)
    monkeypatch.setattr(module, 'WindowsToastRegistration', lambda **_: NS(register=lambda: False))
    _, tray, scheduler, lifecycle = module.build_resident_application(AppConfig.default(tmp_path))
    assert tray is not None and scheduler is not None
    lifecycle.stop(); app.aboutToQuit.disconnect(lifecycle.stop)


def test_main_cleans_up_if_scheduler_start_fails(monkeypatch, tmp_path):
    from university_ai.app import main as module
    calls = []
    def fail(): raise RuntimeError('scheduler failed')
    components = (None, NS(start=lambda: True), NS(start=fail), NS(stop=lambda: calls.append('stop')))
    monkeypatch.setattr(module, 'build_resident_application', lambda _: components)
    assert module.main(tmp_path, run_event_loop=True) == 1
    assert calls == ['stop']


def test_bad_discovery_cannot_redirect_to_external_host(tmp_path):
    file = tmp_path / 'endpoint.json'
    for port in [True, -1, 65536, '80']:
        file.write_text(json.dumps({'v':1,'port':port,'token':'a'*64,'host':'example.com'}))
        with pytest.raises(ValueError): NovaOverlayClient(file)._connect()


def test_notification_failure_and_broken_overlay_preserve_delivery_semantics(tmp_path):
    from datetime import UTC, datetime
    from university_ai.core.rules import NotificationCandidate
    from university_ai.database.database import Database
    from university_ai.database.migrations import migrate
    from university_ai.database.repository import NotificationEventRepository
    from university_ai.database.models import NotificationStatus
    from university_ai.notification.service import NotificationService
    db = Database(tmp_path / 'app.sqlite3'); connection = db.connect(); migrate(connection)
    nova = RecordingClient()
    def fail(_): raise RuntimeError('notification unavailable')
    candidate = NotificationCandidate('test','course',1,datetime.now(UTC),'title','body')
    try:
        service = NotificationService(NotificationEventRepository(connection), NS(send=fail), nova=nova)
        assert service.process([candidate])[0].status == NotificationStatus.FAILED
        assert nova.current_state() == 'error'
        class Broken:
            def set_state(self, _): raise RuntimeError('overlay down')
        delivered = []
        candidate2 = NotificationCandidate('test','course',2,datetime.now(UTC),'title','body')
        service2 = NotificationService(NotificationEventRepository(connection), NS(send=delivered.append), nova=Broken())
        assert service2.process([candidate2])[0].status == NotificationStatus.DELIVERED
        assert len(delivered) == 1
    finally: db.stop()
