"""Opt-in interactive Windows acceptance, isolated data and only owned test processes.

Use Ctrl+Alt+Shift+Space for this test Overlay so an independent resident Overlay
is left untouched. Click its Core and use the real University AI dialogs.
No answers, captured text, credentials or endpoint contents are written to report.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget
from university_ai.app import main as composition
from university_ai.app.commands import ApplicationCommand
from university_ai.app.config import AppConfig
from university_ai.overlay import NovaOverlayClient


def run(overlay_dir):
    overlay_dir = overlay_dir.resolve()
    artifacts = Path('.test-artifacts').resolve(); artifacts.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='core-v2-', dir=artifacts))
    endpoint = root / 'endpoint.json'
    argv = [str(overlay_dir / 'node_modules/electron/dist/electron.exe'), str(overlay_dir), '--integration-smoke']
    os.environ['NOVA_OVERLAY_HOTKEY'] = 'Control+Alt+Shift+Space'
    client = NovaOverlayClient(endpoint, command=argv)
    factory, registration = composition.NovaOverlayClient.from_environment, composition.WindowsToastRegistration
    composition.NovaOverlayClient.from_environment = lambda: client
    composition.WindowsToastRegistration = lambda **_: SimpleNamespace(register=lambda: False)
    try:
        app, tray, scheduler, lifecycle = composition.build_resident_application(AppConfig.default(root))
    finally:
        composition.NovaOverlayClient.from_environment, composition.WindowsToastRegistration = factory, registration
    report = {'commands':[], 'qt_main_thread':True, 'question_answer_seen':False,
              'region_answer_seen':False,'crash_requested':False,'restart_requested':False,
              'states':[], 'human_visual_acceptance':False}
    replacement = None
    dispatcher = tray._dispatcher
    for command, handler in list(dispatcher.handlers.items()):
        def wrapped(command=command, handler=handler):
            report['commands'].append(command.value)
            report['qt_main_thread'] &= QThread.currentThread() == app.thread()
            return handler()
        dispatcher.handlers[command] = wrapped
    controller = tray._capture_controller
    original_result = controller._on_llm_result
    def region_result(text):
        report['region_answer_seen'] = bool(text)
        original_result(text)
    controller._on_llm_result = region_result
    panel = QWidget(); panel.setWindowTitle('NOVA Integration v2 acceptance')
    layout = QVBoxLayout(panel)
    sample = QLabel('NOVA CORE TEST\nWater freezes at zero degrees Celsius.')
    sample.setStyleSheet('background:white;color:black;font-size:25px;padding:22px;')
    layout.addWidget(sample)
    layout.addWidget(QLabel('Test hotkey: Ctrl+Alt+Shift+Space\nUse the Core: AI question, then Region AI.\nCapture only the white sample above.'))
    status = QLabel(); layout.addWidget(status)
    def crash():
        if client._process is not None and client._process.poll() is None:
            client._process.kill(); report['crash_requested'] = True
    def restart():
        nonlocal replacement
        if replacement is not None or client._process is None or client._process.poll() is None:
            return
        env = {**os.environ,'NOVA_OVERLAY_ENDPOINT':str(endpoint)}
        env.pop('NOVA_OVERLAY_OWNER_TOKEN',None); env.pop('ELECTRON_RUN_AS_NODE',None)
        replacement = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        report['restart_requested'] = True
    for label, callback in [('Crash owned test Overlay',crash),('Restart independent test Overlay',restart),
                            ('Open AI question through shared Tray action',lambda: tray.invoke_command(ApplicationCommand.ASK_AI)),
                            ('Finish through University AI graceful shutdown',tray._on_quit)]:
        button = QPushButton(label);button.clicked.connect(callback);layout.addWidget(button)
    state_file = overlay_dir / '.test-profile/integration-native/states.jsonl'
    def update():
        for dialog in tray._dialogs.values():
            if hasattr(dialog,'answer') and dialog._worker is None and dialog.answer.toPlainText().strip():
                report['question_answer_seen'] = True
        try:
            values = [json.loads(line)['state'] for line in state_file.read_text().splitlines() if line]
            for value in values:
                if value not in report['states']:report['states'].append(value)
        except (OSError,ValueError):pass
        report['tray_visible'] = bool(tray._tray and tray._tray.isVisible())
        status.setText('Commands: '+', '.join(report['commands'])+'\nQuestion: '+str(report['question_answer_seen'])+' / Region: '+str(report['region_answer_seen']))
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    timer = QTimer();timer.timeout.connect(update);timer.start(500)
    assert tray.start(); scheduler.start()
    panel.setGeometry(70,80,650,420);panel.show()
    print('Acceptance artifacts: '+str(root),flush=True)
    QTimer.singleShot(20*60*1000,tray._on_quit)
    try:
        app.exec()
    finally:
        lifecycle.stop();timer.stop()
        report['graceful_shutdown'] = lifecycle._stopped
        report['owned_exited'] = client._process is None or client._process.poll() is not None
        report['standalone_preserved'] = replacement is not None and replacement.poll() is None
        if replacement is not None and replacement.poll() is None:
            replacement.terminate();replacement.wait(timeout=30)  # harness owns this test process
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--overlay-dir',type=Path,required=True)
    run(parser.parse_args().overlay_dir)
