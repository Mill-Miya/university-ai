from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from university_ai.database.models import Document, ExtractionStatus
from university_ai.database.repository import DocumentRepository
from university_ai.documents.extractors import extractor_for


class DocumentImportError(ValueError):
    """An input file could not be safely imported into the local store."""


@dataclass(frozen=True)
class ImportResult:
    document: Document
    duplicate: bool = False


class DocumentImportService:
    """Copies a supported file into app-managed storage and extracts local text."""

    _FILE_TYPES = {
        ".pdf": ("PDF", "application/pdf"),
        ".txt": ("TXT", "text/plain"),
        ".docx": ("DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".png": ("PNG", "image/png"),
        ".jpg": ("JPG", "image/jpeg"),
        ".jpeg": ("JPEG", "image/jpeg"),
    }

    def __init__(self, repository: DocumentRepository, storage_directory: Path) -> None:
        self._repository = repository
        self._storage_directory = storage_directory
        self._logger = logging.getLogger(__name__)

    def import_file(self, source_path: Path) -> ImportResult:
        source = Path(source_path)
        if not source.is_file():
            raise DocumentImportError("document source must be an existing file")
        try:
            file_type, mime_type = self._FILE_TYPES[source.suffix.lower()]
        except KeyError as error:
            raise DocumentImportError(f"unsupported document type: {source.suffix or '(none)'}") from error

        digest = self._sha256(source)
        existing = self._repository.get_by_sha256(digest)
        if existing is not None:
            return ImportResult(existing, duplicate=True)

        destination = self._storage_directory / digest[:2] / f"{digest}{source.suffix.lower()}"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(source, destination)
        except OSError as error:
            self._logger.exception("Document copy failed")
            raise DocumentImportError("document could not be copied into local storage") from error

        stat = source.stat()
        document = Document(
            id=None,
            title=source.stem,
            source_path=str(source.resolve()),
            stored_path=str(destination.resolve()),
            file_type=file_type,
            mime_type=mime_type,
            size_bytes=stat.st_size,
            sha256=digest,
            imported_at=datetime.now(UTC),
            modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            metadata_json=json.dumps({"original_filename": source.name}),
        )
        try:
            stored = self._repository.create(document)
        except sqlite3.IntegrityError:
            existing = self._repository.get_by_sha256(digest)
            if existing is not None:
                return ImportResult(existing, duplicate=True)
            raise

        extractor = extractor_for(file_type)
        if extractor is None:
            return ImportResult(stored)
        try:
            text = extractor.extract(destination)
            return ImportResult(self._repository.update_extraction(stored.id or 0, ExtractionStatus.EXTRACTED, extracted_text=text))
        except Exception as error:
            self._logger.warning("Document text extraction failed for type=%s: %s", file_type, type(error).__name__)
            return ImportResult(
                self._repository.update_extraction(stored.id or 0, ExtractionStatus.FAILED, extraction_error=str(error))
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as error:
            raise DocumentImportError("document could not be read") from error
        return digest.hexdigest()
