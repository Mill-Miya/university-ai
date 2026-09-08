from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QListWidget, QMessageBox, QPushButton, QVBoxLayout

from university_ai.documents.import_service import DocumentImportError, DocumentImportService


class DocumentPresenter:
    """Headless document view data; Qt never accesses SQLite directly."""

    def __init__(self, repository, import_service: DocumentImportService) -> None:
        self._repository = repository
        self._import_service = import_service

    def list_documents(self) -> list[str]:
        return [f"{item.title} | {item.file_type} | {item.extraction_status}" for item in self._repository.list()]

    def import_file(self, path: Path):
        return self._import_service.import_file(path)


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
        close_button = QPushButton("閉じる")
        add_button.clicked.connect(self._add_file)
        close_button.clicked.connect(self.accept)
        controls.addWidget(add_button); controls.addWidget(close_button)
        layout.addLayout(controls)
        self._refresh()

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
