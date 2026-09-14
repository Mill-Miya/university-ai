from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QListWidget, QMessageBox, QPushButton, QVBoxLayout

from university_ai.documents.import_service import DocumentImportError, DocumentImportService


class DocumentPresenter:
    """Headless document view data; Qt never accesses SQLite directly."""

    def __init__(self, repository, import_service: DocumentImportService, indexing_service=None) -> None:
        self._repository = repository
        self._import_service = import_service
        self._indexing_service = indexing_service

    def list_documents(self) -> list[str]:
        result = []
        for item in self._repository.list():
            index_status = ""
            if self._indexing_service is not None:
                index_status = " | INDEXED" if self._indexing_service.is_indexed(item.id or 0) else " | NOT_INDEXED"
            result.append(f"{item.title} | {item.file_type} | {item.extraction_status}{index_status}")
        return result

    def import_file(self, path: Path):
        return self._import_service.import_file(path)

    def documents(self):
        return self._repository.list()

    def index_document(self, document_id: int, *, force: bool = False):
        if self._indexing_service is None:
            raise RuntimeError("indexing is unavailable")
        return self._indexing_service.index_document(document_id, force=force)


class DocumentIndexWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)
    def __init__(self, presenter: DocumentPresenter, document_id: int) -> None:
        super().__init__(); self._presenter, self._document_id = presenter, document_id
    def run(self) -> None:
        try: self.completed.emit(self._presenter.index_document(self._document_id))
        except Exception: self.failed.emit("資料のインデックス作成に失敗しました。")


class DocumentsDialog(QDialog):
    def __init__(self, presenter: DocumentPresenter, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("資料")
        self._presenter = presenter
        self._logger = logging.getLogger(__name__)
        layout = QVBoxLayout(self)
        self._items = QListWidget()
        layout.addWidget(self._items)
        controls = QHBoxLayout()
        add_button = QPushButton("ファイル追加")
        index_button = QPushButton("インデックス")
        close_button = QPushButton("閉じる")
        add_button.clicked.connect(self._add_file)
        close_button.clicked.connect(self.accept)
        controls.addWidget(add_button); controls.addWidget(index_button); controls.addWidget(close_button)
        layout.addLayout(controls)
        self._refresh()
        self._index_worker = None
        index_button.clicked.connect(self._index_selected)

    def _refresh(self) -> None:
        self._items.clear()
        self._items.addItems(self._presenter.list_documents())

    def _add_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "資料を追加",
            "",
            "Supported files (*.pdf *.txt *.docx *.png *.jpg *.jpeg)",
        )
        if not path:
            return
        try:
            result = self._presenter.import_file(Path(path))
        except (DocumentImportError, OSError) as error:
            self._logger.warning("Document import failed: %s", type(error).__name__)
            QMessageBox.warning(self, "資料", "資料を追加できませんでした。")
            return
        self._refresh()
        QMessageBox.information(self, "資料", "同一ファイルは既に登録済みです。" if result.duplicate else "資料を追加しました。")

    def _index_selected(self) -> None:
        row = self._items.currentRow(); documents = self._presenter.documents()
        if row < 0 or row >= len(documents) or self._index_worker is not None:
            return
        self._index_worker = DocumentIndexWorker(self._presenter, documents[row].id or 0)
        self._index_worker.completed.connect(self._indexed); self._index_worker.failed.connect(self._index_failed)
        self._index_worker.start()

    def _indexed(self, result) -> None:
        self._refresh(); self._index_worker = None
        QMessageBox.information(self, "資料", "インデックスを作成しました。" if result.indexed else "インデックスを作成できませんでした。")

    def _index_failed(self, _message: str) -> None:
        self._index_worker = None
        QMessageBox.warning(self, "資料", "インデックスを作成できませんでした。")
