from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from university_ai.database.models import ExtractionStatus, OcrResult, OcrSourceType, OcrStatus


class OcrServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrServiceResult:
    result: OcrResult
    duplicate: bool = False


class OcrService:
    """Validates local sources, persists attempts, and delegates only to an OCR engine."""

    _IMAGE_TYPES = {"PNG", "JPG", "JPEG"}

    def __init__(self, results, documents, captures, engine) -> None:
        self._results = results
        self._documents = documents
        self._captures = captures
        self._engine = engine
        self._logger = logging.getLogger(__name__)

    def recognize_capture(self, capture_id: int, *, language: str = "jpn+eng", force: bool = False) -> OcrServiceResult:
        capture = self._captures.get(capture_id)
        if capture is None:
            raise OcrServiceError("screen capture was not found")
        return self._recognize(OcrSourceType.SCREEN_CAPTURE, capture_id, Path(capture.stored_path), language, force)

    def recognize_document(self, document_id: int, *, language: str = "jpn+eng", force: bool = False) -> OcrServiceResult:
        document = self._documents.get(document_id)
        if document is None:
            raise OcrServiceError("document was not found")
        if document.file_type not in self._IMAGE_TYPES:
            raise OcrServiceError("OCR supports imported PNG, JPG, and JPEG documents only")
        outcome = self._recognize(OcrSourceType.DOCUMENT, document_id, Path(document.stored_path), language, force)
        if outcome.result.status is OcrStatus.EXTRACTED:
            self._documents.update_extraction(document_id, ExtractionStatus.EXTRACTED, extracted_text=outcome.result.text)
        elif not outcome.duplicate:
            self._documents.update_extraction(document_id, ExtractionStatus.FAILED, extraction_error=outcome.result.error)
        return outcome

    def _recognize(self, source_type: OcrSourceType, source_id: int, path: Path, language: str, force: bool) -> OcrServiceResult:
        existing = self._results.list_for_source(source_type, source_id)
        if not force and existing and existing[0].status is OcrStatus.EXTRACTED:
            return OcrServiceResult(existing[0], duplicate=True)
        pending = self._results.create(OcrResult(None, source_type, source_id, OcrStatus.PENDING, datetime.now(UTC)))
        try:
            recognized = self._engine.recognize_image(path, language=language)
            result = OcrResult(pending.id, source_type, source_id, OcrStatus.EXTRACTED, datetime.now(UTC),
                               text=recognized.text, language=recognized.language, engine=recognized.engine,
                               metadata_json=recognized.metadata_json)
        except Exception as error:
            self._logger.warning("Local OCR failed for %s/%s: %s", source_type, source_id, type(error).__name__)
            result = OcrResult(pending.id, source_type, source_id, OcrStatus.FAILED, datetime.now(UTC), error=str(error))
        return OcrServiceResult(self._results.update(result))
