import json
import socket
import threading
import time
from types import SimpleNamespace as NS

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QDialog

from university_ai.app.commands import ApplicationCommand as C, ApplicationCommandDispatcher, CommandIntent
from university_ai.overlay.channel import CommandChannel
from university_ai.ui.tray import SystemTrayController


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('command', list(C))
def test_known_command_on_qt_thread(app, command):
    threads, replies = [], []
    dispatcher = ApplicationCommandDispatcher({command: lambda: threads.append(QThread.currentThread())})
    connected = threading.Event(); connected.set()
    thread = threading.Thread(target=lambda: dispatcher.submit(CommandIntent(command, connected, time.monotonic()+3, replies.append)))
    thread.start(); thread.join()
    assert threads == []
    app.processEvents()
    assert threads == [app.thread()] and replies == [None]


def test_dispatch_failure_unknown_busy_shutdown(app):
    calls = []
    dispatcher = ApplicationCommandDispatcher({C.ASK_AI: lambda: calls.append(True)})
    assert dispatcher.invoke('arbitrary_method') == 'invalid'
    assert dispatcher.invoke(C.ASK_AI) is None
    assert dispatcher.invoke(C.ASK_AI) == 'busy'
    assert calls == [True]
    dispatcher.stop()
    assert dispatcher.invoke(C.ASK_AI) == 'unavailable'
    def fail(): raise RuntimeError('private traceback')
    assert ApplicationCommandDispatcher({C.ASK_AI: fail}).invoke(C.ASK_AI) == 'failed'


def test_qt_queue_bounded_across_sessions(app):
    connected = threading.Event(); connected.set()
    calls, replies = [], []
    dispatcher = ApplicationCommandDispatcher({C.ASK_AI: lambda: calls.append(True)})
    intent = CommandIntent(C.ASK_AI, connected, time.monotonic()+3, replies.append)
    dispatcher.submit(intent)
    dispatcher.submit(intent)
    assert replies == ['busy']
    app.processEvents()
    assert calls == [True] and replies == ['busy', None]


@pytest.mark.parametrize('expired', [False, True])
def test_stale_queued_intent_never_executes(app, expired):
    calls = []; connected = threading.Event()
    if expired: connected.set()
    dispatcher = ApplicationCommandDispatcher({C.ASK_AI: lambda: calls.append(True)})
    dispatcher.submit(CommandIntent(C.ASK_AI, connected, time.monotonic() - 1 if expired else time.monotonic()+3, calls.append))
    app.processEvents()
    assert calls == []


def packet(**changes):
    return {'v':1,'op':'command','token':'a'*64,'request_id':1,'command':'ask_ai',**changes}


@pytest.mark.parametrize('changes', [{'command':'exec'}, {'command':[]}, {'path':'C:/secret'}, {'token':'b'*64}, {'request_id':True}, {'request_id':0}, {'v':True}, {'op':'eval'}])
def test_malformed_command_rejected(changes):
    channel = CommandChannel(None, 'a'*64, NS(submit=lambda _: pytest.fail('must not dispatch')))
    with pytest.raises(ConnectionError): channel._command(packet(**changes))


def test_duplex_reply_duplicate_disconnect_reconnect_no_replay(app):
    calls = []; dispatcher = ApplicationCommandDispatcher({C.ASK_AI: lambda: calls.append('ask')})
    left, right = socket.socketpair()
    left.settimeout(.5); right.settimeout(.5)
    channel = CommandChannel(left, 'a'*64, dispatcher)
    try:
        channel._command(packet())
        app.processEvents()
        result = channel.results.get_nowait()
        assert result == {'v':1,'op':'command_result','token':'a'*64,'request_id':1,'command':'ask_ai','ok':True}
        with pytest.raises(ConnectionError): channel._command(packet())
        channel.close()
        second = CommandChannel(left, 'a'*64, dispatcher)
        dispatcher._last = -float('inf')
        second._command(packet())
        second.close()
        app.processEvents()
        assert calls == ['ask']  # queued intent invalidated by disconnect
        third = CommandChannel(left, 'a'*64, dispatcher)
        app.processEvents()
        assert calls == ['ask']  # reconnect does not replay
        third._command(packet())
        app.processEvents()
        assert calls == ['ask','ask']
        right.close()
        with pytest.raises(ConnectionError): third.pump()
    finally:
        left.close(); right.close()


def test_interleaved_command_before_state_ack(app):
    intents = []; left, right = socket.socketpair(); left.settimeout(.5)
    channel = CommandChannel(left, 'a'*64, NS(submit=intents.append))
    try:
        right.sendall((json.dumps(packet())+'\n'+json.dumps({'v':1,'ok':True})+'\n').encode())
        channel.exchange({'v':1,'op':'state','token':'a'*64,'state':'idle'})
        assert len(intents) == 1
        assert json.loads(right.recv(4096))['op'] == 'state'
    finally:
        channel.close(); left.close(); right.close()


def test_tray_core_share_existing_dialog_and_region_handler(app):
    created, regions = [], []
    def factory():
        dialog = QDialog(); created.append(dialog); return dialog
    tray = SystemTrayController(None, factory, lambda: None, factory, factory)
    tray.set_capture_controller(NS(_overlay=None, _llm_workers=set(), _ocr_service=object(), _llm_service=object(), select_region_and_ask=lambda: regions.append(True)))
    dispatcher = ApplicationCommandDispatcher(tray.command_handlers())
    tray.set_command_dispatcher(dispatcher)
    assert tray.invoke_command(C.ASK_AI) is None
    dispatcher._last = -float('inf')
    assert dispatcher.invoke(C.ASK_AI) == 'busy'
    assert len(created) == 1
    created[0].reject()
    dispatcher._last = -float('inf')
    assert dispatcher.invoke(C.ASK_REGION) is None
    assert regions == [True]
