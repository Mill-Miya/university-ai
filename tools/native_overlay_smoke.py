"""Opt-in Windows integration test using real Qt capture, Tesseract and Ollama.

Run from the university-ai root with --overlay-dir <nova repo>/overlay-prototype.
Captures only its own sample window and keeps test data under .test-artifacts.
Requires the matching Integration v1 overlay, including --integration-smoke.
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

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from university_ai.app import main as composition
from university_ai.app.config import AppConfig
from university_ai.capture.backend import CaptureRectangle
from university_ai.overlay import NovaOverlayAdapter, NovaOverlayClient
from university_ai.ui.llm import LlmWorker


def run(overlay_dir: Path):
    overlay_dir = overlay_dir.resolve()
    executable = overlay_dir / 'node_modules/electron/dist/electron.exe'
    assert executable.is_file(), 'Install the overlay dependencies first'
    artifacts = Path('.test-artifacts').resolve(); artifacts.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='native-', dir=artifacts))
    endpoint = root / 'endpoint.json'
    command = [str(executable), str(overlay_dir), '--integration-smoke']
    client = NovaOverlayClient(endpoint, command=command)
    original_factory = composition.NovaOverlayClient.from_environment
    original_registration = composition.WindowsToastRegistration
    # Preserve the user's Start-menu registration and all application data.
    composition.NovaOverlayClient.from_environment = lambda: client
    composition.WindowsToastRegistration = lambda **_: SimpleNamespace(register=lambda: False)
    app, tray, scheduler, lifecycle = composition.build_resident_application(AppConfig.default(root))
    composition.NovaOverlayClient.from_environment = original_factory
    composition.WindowsToastRegistration = original_registration
    state_file = overlay_dir / '.test-profile/integration-native/states.jsonl'
    report = {'root': str(root), 'checks': [], 'manual_visual_review': False}
    replacement = None
    owned_check = None
    sample = None
    dialogs = []

    def states():
        try: return [json.loads(line)['state'] for line in state_file.read_text().splitlines() if line]
        except (OSError, ValueError): return []

    def until(predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            if time.monotonic() >= deadline: raise AssertionError('Native integration timed out; states=' + repr(states()))
            time.sleep(.03)
        app.processEvents()

    def state(value, timeout=20):
        until(lambda: bool(states()) and states()[-1] == value, timeout)

    def dismiss_results():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QMessageBox): widget.accept()

    dismiss = QTimer(); dismiss.timeout.connect(dismiss_results); dismiss.start(200)
    try:
        assert tray.start(), 'Windows System Tray unavailable'
        scheduler.start()
        until(lambda: endpoint.is_file() and client._process is not None)
        state('idle'); report['checks'].append('startup -> rendered idle')

        question = tray._llm_factory(); dialogs.append(question)
        question.show(); state('active')
        question.input.setPlainText('Reply with exactly: NOVA integration ready.')
        question._ask(); state('thinking')
        until(lambda: question._worker is None, 180)
        assert question.answer.toPlainText().strip() and '現在利用できません' not in question.answer.toPlainText()
        state('notification'); state('idle'); question.accept()
        report['checks'].append('real Ollama question -> thinking -> notification -> idle; answer remains in Qt')

        sample = QLabel('NOVA INTEGRATION TEST\nExplain this sentence: Water freezes at zero degrees Celsius.')
        sample.setStyleSheet('background:white;color:black;font-size:24px;padding:24px;')
        sample.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        sample.setGeometry(80,100,950,220); sample.show(); sample.raise_(); sample.activateWindow()
        for _ in range(15): app.processEvents(); time.sleep(.05)
        geometry = sample.frameGeometry()
        screen = app.primaryScreen().geometry()
        rectangle = CaptureRectangle(geometry.x()-screen.x(), geometry.y()-screen.y(), geometry.width(), geometry.height())
        controller = tray._capture_controller
        controller.select_region_and_ask()
        state('scanning')
        QTest.keyClick(controller._overlay, Qt.Key.Key_Escape)
        assert controller._overlay is None
        state('idle')
        report['checks'].append('native Qt region-selection Escape -> cancellation -> idle')
        answers, failures = [], []
        original_result = controller._on_llm_result
        controller._on_llm_result = lambda text: (answers.append(text), original_result(text))
        controller._on_failure = failures.append
        checkpoint = len(states())
        QTimer.singleShot(0, lambda: controller._capture_region_and_ask(rectangle))
        # Synchronous OCR can finish before the Qt pump returns; verify the actual
        # recorded renderer transitions instead of requiring the transient still live.
        until(lambda: 'scanning' in states()[checkpoint:], 90)
        until(lambda: 'thinking' in states()[checkpoint:], 90)
        until(lambda: bool(answers) or bool(failures), 180)
        assert answers and not failures, failures
        until(lambda: 'notification' in states()[checkpoint:]); state('idle')
        report['checks'].append('real Qt sample capture -> Tesseract OCR -> Ollama -> notification -> idle; QMessageBox retained')

        worker = LlmWorker(action=lambda: (_ for _ in ()).throw(RuntimeError('deliberate test failure')), nova=client)
        worker.start(); state('error'); until(lambda: not worker.isRunning()); state('idle')
        report['checks'].append('recoverable worker failure -> error -> idle')

        owned = client._process
        report['initial_rendered_states'] = states()
        owned.kill()
        # Windows may take time to tear down the GPU/renderer job after termination.
        until(lambda: owned.poll() is not None, 30)
        assert tray._tray.isVisible()
        question = tray._llm_factory(); dialogs.append(question)
        question.input.setPlainText('Reply with exactly: Still running.')
        question._ask(); until(lambda: question._worker is None, 180)
        assert question.answer.toPlainText().strip() and '現在利用できません' not in question.answer.toPlainText()
        question.accept()
        report['checks'].append('forced Overlay termination: University AI tray and real LLM still work')

        # Restart independently: University AI must reconnect but must not own/kill it.
        env = {**os.environ, 'NOVA_OVERLAY_ENDPOINT':str(endpoint)}
        env.pop('NOVA_OVERLAY_OWNER_TOKEN', None); env.pop('ELECTRON_RUN_AS_NODE', None)
        replacement = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        token = client.begin('thinking'); state('thinking', 30)
        client.finish(token); state('idle')
        lifecycle.stop(); assert replacement.poll() is None
        report['checks'].append('reconnect to independently restarted Overlay; University AI shutdown preserves it')
        replacement.terminate(); replacement.wait(timeout=30)
        owned_check = NovaOverlayClient(endpoint, command=command)
        owned_check.start()
        until(lambda: owned_check._process is not None, 30)
        owned_check.active(); state('active', 30)
        owned_check.stop()
        until(lambda: owned_check._process.poll() is not None, 30)
        report['checks'].append('owned Overlay exits on client shutdown')
        report['passed'] = True
    finally:
        lifecycle.stop(); dismiss.stop()
        if owned_check is not None: owned_check.stop()
        if sample is not None: sample.close()
        for dialog in dialogs: dialog.close()
        if replacement is not None and replacement.poll() is None:
            replacement.terminate(); replacement.wait(timeout=30)
        report['rendered_states'] = states()
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--overlay-dir', type=Path, required=True)
    run(parser.parse_args().overlay_dir)
