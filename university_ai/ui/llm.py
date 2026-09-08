from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

class LlmWorker(QThread):
    completed=Signal(str); failed=Signal(str)
    def __init__(self, service=None, prompt=None, *, action=None): super().__init__(); self._service,self._prompt,self._action=service,prompt,action
    def run(self):
        try: self.completed.emit((self._action() if self._action else self._service.ask(self._prompt)).text)
        except Exception: self.failed.emit('ローカルAIは現在利用できません。')

class AiQuestionDialog(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent); self.setWindowTitle('AIに質問'); self._service=service; self._worker=None
        layout=QVBoxLayout(self); layout.addWidget(QLabel('質問'))
        self.input=QTextEdit(); self.input.setPlaceholderText('ガウスの法則を簡単に説明して'); layout.addWidget(self.input)
        self.answer=QTextEdit(); self.answer.setReadOnly(True); layout.addWidget(self.answer)
        buttons=QHBoxLayout(); self.ask_button=QPushButton('質問'); close=QPushButton('閉じる'); buttons.addWidget(self.ask_button); buttons.addWidget(close); layout.addLayout(buttons)
        self.ask_button.clicked.connect(self._ask); close.clicked.connect(self.accept)
    def _ask(self):
        prompt=self.input.toPlainText().strip()
        if not prompt or self._worker is not None: return
        self.ask_button.setEnabled(False); self.answer.setPlainText('生成中…')
        self._worker=LlmWorker(self._service,prompt); self._worker.completed.connect(self._done); self._worker.failed.connect(self._failed); self._worker.start()
    def _done(self,text): self.answer.setPlainText(text); self._finish()
    def _failed(self,message): self.answer.setPlainText(message); self._finish()
    def _finish(self): self.ask_button.setEnabled(True); self._worker=None
