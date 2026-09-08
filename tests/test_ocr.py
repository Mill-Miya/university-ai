from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from university_ai.capture.service import CaptureStorageService, ScreenCaptureService
from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.models import CaptureType, Document, ExtractionStatus, OcrResult, OcrSourceType, OcrStatus, ScreenCapture
from university_ai.database.repository import DocumentRepository, OcrResultRepository, ScreenCaptureRepository
from university_ai.ocr.engine import RecognizedText
from university_ai.ocr.service import OcrService, OcrServiceError
from university_ai.ui.capture import ScreenCaptureController


class FakeEngine:
    def __init__(self, text="電磁気学 第3回 ガウスの法則\nControl Systems Assignment 2"):
        self.text, self.calls, self.error = text, [], None
    def recognize_image(self, path, *, language):
        self.calls.append((Path(path), language))
        if self.error:
            raise self.error
        return RecognizedText(self.text, language, "fake-local", json.dumps({"lines": []}))


@pytest.fixture
def ocr_services(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    connection = database.connect(); migrate(connection)
    documents, captures, results = DocumentRepository(connection), ScreenCaptureRepository(connection), OcrResultRepository(connection)
    image = tmp_path / "source.png"; image.write_bytes(b"local image")
    document = documents.create(Document(None, "image", str(image), str(image), "PNG", "image/png", image.stat().st_size,
        "a" * 64, datetime.now(UTC), datetime.now(UTC), metadata_json="{}"))
    capture = captures.create(ScreenCapture(None, CaptureType.REGION, str(image), 100, 50, datetime.now(UTC), metadata_json="{}"))
    engine = FakeEngine(); service = OcrService(results, documents, captures, engine)
    yield database, documents, captures, results, document, capture, engine, service
    database.stop()


def test_migration_v5_and_ocr_repository_persistence(ocr_services, tmp_path):
    database, _documents, _captures, results, _document, capture, _engine, _service = ocr_services
    stored = results.create(OcrResult(None, OcrSourceType.SCREEN_CAPTURE, capture.id or 0, OcrStatus.EXTRACTED,
        datetime.now(UTC), text="日本語 English", language="jpn+eng", engine="fake-local", metadata_json="{}"))
    assert results.get(stored.id or 0) == stored
    with pytest.raises(ValueError, match="Timezone-aware"):
        results.create(OcrResult(None, OcrSourceType.SCREEN_CAPTURE, 1, OcrStatus.PENDING, datetime.now()))
    database.stop()
    reopened = Database(tmp_path / "app.sqlite3"); connection = reopened.connect(); migrate(connection)
    assert OcrResultRepository(connection).get(stored.id or 0) == stored
    reopened.stop()


def test_capture_and_imported_image_ocr_updates_representative_document_text(ocr_services):
    _database, documents, _captures, results, document, capture, engine, service = ocr_services
    capture_result = service.recognize_capture(capture.id or 0)
    document_result = service.recognize_document(document.id or 0)
    assert capture_result.result.status is OcrStatus.EXTRACTED
    assert document_result.result.text == engine.text
    assert documents.get(document.id or 0).extraction_status is ExtractionStatus.EXTRACTED
    assert documents.get(document.id or 0).extracted_text == engine.text
    assert len(results.list_for_source(OcrSourceType.SCREEN_CAPTURE, capture.id or 0)) == 1
    assert engine.calls[0][1] == "jpn+eng"


def test_duplicate_and_force_reocr_semantics(ocr_services):
    _database, _documents, _captures, results, _document, capture, engine, service = ocr_services
    first = service.recognize_capture(capture.id or 0)
    duplicate = service.recognize_capture(capture.id or 0)
    forced = service.recognize_capture(capture.id or 0, force=True)
    assert not first.duplicate and duplicate.duplicate and not forced.duplicate
    assert len(results.list_for_source(OcrSourceType.SCREEN_CAPTURE, capture.id or 0)) == 2
    assert len(engine.calls) == 2


def test_ocr_failure_missing_image_and_unsupported_document_are_safe(ocr_services):
    _database, documents, captures, results, document, capture, engine, service = ocr_services
    engine.error = RuntimeError("engine unavailable")
    failed = service.recognize_capture(capture.id or 0)
    assert failed.result.status is OcrStatus.FAILED and failed.result.error
    Path(capture.stored_path).unlink()
    missing = service.recognize_capture(capture.id or 0, force=True)
    assert missing.result.status is OcrStatus.FAILED
    text_path = Path(document.stored_path).with_suffix(".txt"); text_path.write_text("text", encoding="utf-8")
    text_document = documents.create(Document(None, "text", str(text_path), str(text_path), "TXT", "text/plain", 4,
        "b" * 64, datetime.now(UTC), datetime.now(UTC), metadata_json="{}"))
    with pytest.raises(OcrServiceError, match="PNG"):
        service.recognize_document(text_document.id or 0)
    with pytest.raises(OcrServiceError, match="not found"):
        service.recognize_document(999)
    assert results.list_for_source(OcrSourceType.DOCUMENT, text_document.id or 0) == []


def test_region_capture_to_ocr_controller_wiring():
    events = []
    class CaptureService:
        def capture_region(self, _rectangle): return type("Result", (), {"capture": type("Capture", (), {"id": 7, "stored_path": "capture.png"})()})()
    class Ocr:
        def recognize_capture(self, capture_id):
            assert capture_id == 7
            return type("Outcome", (), {"result": type("Result", (), {"status": OcrStatus.EXTRACTED, "text": "電子回路1 Report Deadline 9/30"})()})()
    class Overlay:
        def __init__(self, selected, cancelled): self.selected, self.cancelled = selected, cancelled
        def show(self): pass
        def raise_(self): pass
        def activateWindow(self): pass
    holder = {}
    def factory(selected, cancelled): holder["overlay"] = Overlay(selected, cancelled); return holder["overlay"]
    controller = ScreenCaptureController(CaptureService(), overlay_factory=factory, ocr_service=Ocr(),
        on_success=events.append, on_ocr_result=events.append, on_failure=events.append)
    controller.select_region_and_ocr()
    holder["overlay"].selected(type("Rect", (), {})())
    assert events == ["保存しました: capture.png", "電子回路1 Report Deadline 9/30"]
