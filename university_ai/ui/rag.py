from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout


class RagWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service, question: str) -> None:
        super().__init__()
        self._service, self._question = service, question

    def run(self) -> None:
        try:
            self.completed.emit(self._service.answer(self._question))
        except Exception:
            self.failed.emit("資料検索は現在利用できません。")


class RagQuestionDialog(QDialog):
    """Minimal, non-blocking local-document question UI."""
    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("資料について質問")
        self._service, self._worker = service, None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("質問"))
        self.input = QTextEdit(); self.input.setPlaceholderText("資料について質問してください")
        self.answer = QTextEdit(); self.answer.setReadOnly(True)
        self.sources = QTextEdit(); self.sources.setReadOnly(True)
        layout.addWidget(self.input); layout.addWidget(QLabel("回答")); layout.addWidget(self.answer)
        layout.addWidget(QLabel("参照")); layout.addWidget(self.sources)
        buttons = QHBoxLayout(); self.ask_button = QPushButton("資料を検索"); close = QPushButton("閉じる")
        buttons.addWidget(self.ask_button); buttons.addWidget(close); layout.addLayout(buttons)
        self.ask_button.clicked.connect(self._ask); close.clicked.connect(self.accept)

    def _ask(self) -> None:
        question = self.input.toPlainText().strip()
        if not question or self._worker is not None:
            return
        self.ask_button.setEnabled(False); self.answer.setPlainText("検索・生成中…"); self.sources.clear()
        self._worker = RagWorker(self._service, question)
        self._worker.completed.connect(self._done); self._worker.failed.connect(self._failed); self._worker.start()

    def _done(self, response) -> None:
        self.answer.setPlainText(response.answer)
        self.sources.setPlainText("\n".join(
            f"- {source.filename}" + (f" / p.{source.page}" if source.page else "") + f" (chunk {source.chunk_index}, score {source.score:.3f})"
            for source in response.sources
        ))
        self._finish()

    def _failed(self, message: str) -> None:
        self.answer.setPlainText(message); self._finish()

    def _finish(self) -> None:
        self.ask_button.setEnabled(True); self._worker = None
