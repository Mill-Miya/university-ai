from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout
from university_ai.overlay import NovaOverlayAdapter

class LlmWorker(QThread):
    completed=Signal(str); failed=Signal(str)
    def __init__(self, service=None, prompt=None, *, action=None, nova=None):
        super().__init__(); self._service,self._prompt,self._action=service,prompt,action
        self._nova = NovaOverlayAdapter(nova)
    def run(self):
        token = self._nova.begin('thinking')
        try:
            answer = (self._action() if self._action else self._service.ask(self._prompt)).text
        except Exception:
            self._nova.finish(token, 'error')
            self.failed.emit('ローカルAIは現在利用できません。')
        else:
            self._nova.finish(token, 'notification')
            self.completed.emit(answer)

class AiQuestionDialog(QDialog):
    def __init__(self, service, parent=None, *, nova=None):
        super().__init__(parent); self.setWindowTitle('AIに質問'); self._service=service; self._worker=None
        self._nova = NovaOverlayAdapter(nova)
        self._invoke_token = self._nova.begin('active')
        self.finished.connect(lambda _: self._nova.finish(self._invoke_token))
        layout=QVBoxLayout(self); layout.addWidget(QLabel('質問'))
        self.input=QTextEdit(); self.input.setPlaceholderText('ガウスの法則を簡単に説明して'); layout.addWidget(self.input)
        self.answer=QTextEdit(); self.answer.setReadOnly(True); layout.addWidget(self.answer)
        buttons=QHBoxLayout(); self.ask_button=QPushButton('質問'); close=QPushButton('閉じる'); buttons.addWidget(self.ask_button); buttons.addWidget(close); layout.addLayout(buttons)
        self.ask_button.clicked.connect(self._ask); close.clicked.connect(self.accept)
    def _ask(self):
        prompt=self.input.toPlainText().strip()
        if not prompt or self._worker is not None: return
        self.ask_button.setEnabled(False); self.answer.setPlainText('生成中…')
        self._nova.finish(self._invoke_token)
        self._worker=LlmWorker(self._service,prompt,nova=self._nova); self._worker.completed.connect(self._done); self._worker.failed.connect(self._failed)
        self._worker.setParent(QApplication.instance())
        self._worker.finished.connect(self._finish)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
    def _done(self,text): self.answer.setPlainText(text)
    def _failed(self,message): self.answer.setPlainText(message)
    def _finish(self): self.ask_button.setEnabled(True); self._worker=None
