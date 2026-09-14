from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from university_ai.database.models import DocumentChunk, ExtractionStatus
from university_ai.rag.chunker import DocumentChunker


@dataclass(frozen=True)
class IndexingResult:
    document_id: int
    chunk_count: int
    indexed: bool
    skipped: bool = False
    error: str | None = None
    duration_seconds: float = 0.0


class DocumentIndexingService:
    """Explicit document-to-vector indexing, preserving Document as the source of truth."""
    def __init__(self, documents, chunks, embedding_engine, chunker: DocumentChunker | None = None) -> None:
        self._documents, self._chunks, self._embedding = documents, chunks, embedding_engine
        self._chunker = chunker or DocumentChunker()
        self._logger = logging.getLogger(__name__)

    def index_document(self, document_id: int, *, force: bool = False) -> IndexingResult:
        started = time.monotonic()
        document = self._documents.get(document_id)
        if document is None:
            return IndexingResult(document_id, 0, False, error="document was not found", duration_seconds=time.monotonic() - started)
        if document.extraction_status is not ExtractionStatus.EXTRACTED or not (document.extracted_text or "").strip():
            return IndexingResult(document_id, 0, False, skipped=True, error="document has no extracted text", duration_seconds=time.monotonic() - started)
        existing = self._chunks.list_for_document(document_id)
        if existing and not force:
            return IndexingResult(document_id, len(existing), False, skipped=True, duration_seconds=time.monotonic() - started)
        try:
            text_chunks = self._chunker.chunk(document.extracted_text or "")
            if not text_chunks:
                return IndexingResult(document_id, 0, False, skipped=True, error="document has no indexable text", duration_seconds=time.monotonic() - started)
            vectors = self._embedding.embed([chunk.text for chunk in text_chunks])
            if len(vectors) != len(text_chunks):
                raise ValueError("embedding count does not match chunk count")
            source_name = json.loads(document.metadata_json).get("original_filename", document.title)
            now = datetime.now(UTC)
            records = [DocumentChunk(None, document_id, chunk.index, chunk.text, tuple(vector), self._embedding.model,
                self._embedding.runtime, now, metadata_json=json.dumps({"source_filename": source_name, "source_type": "DOCUMENT"}, ensure_ascii=False))
                for chunk, vector in zip(text_chunks, vectors, strict=True)]
            stored = self._chunks.replace_for_document(document_id, records)
            return IndexingResult(document_id, len(stored), True, duration_seconds=time.monotonic() - started)
        except Exception as error:
            self._logger.warning("Document indexing failed for document_id=%s: %s", document_id, type(error).__name__)
            return IndexingResult(document_id, 0, False, error="document indexing failed", duration_seconds=time.monotonic() - started)

    def is_indexed(self, document_id: int) -> bool:
        return bool(self._chunks.list_for_document(document_id))
