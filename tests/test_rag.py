from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime

from university_ai.database.database import Database
from university_ai.database.migrations import migrate
from university_ai.database.models import Document, DocumentChunk, ExtractionStatus
from university_ai.database.repository import DocumentChunkRepository, DocumentRepository
from university_ai.llm.models import LlmResponse
from university_ai.rag.chunker import DocumentChunker
from university_ai.rag.indexing import DocumentIndexingService
from university_ai.rag.retriever import Retriever
from university_ai.rag.service import RagService


class FakeEmbedding:
    runtime = "fake-local"
    model = "fake-embed"
    def __init__(self): self.fail = False; self.calls = []
    def availability(self): return True
    def embed(self, texts):
        if self.fail: raise RuntimeError("embedding unavailable")
        self.calls.append(list(texts))
        return [[1.0, 0.0] if any(word in text for word in ("Deadline", "期限", "9/30")) else [0.0, 1.0] for text in texts]


class FakeLlm:
    def __init__(self): self.calls = []; self.fail = False
    def ask(self, prompt, **options):
        if self.fail: raise RuntimeError("LLM unavailable")
        self.calls.append((prompt, options))
        return LlmResponse("資料に基づく回答", "fake-local", "fake", datetime.now(UTC), .01)


def make_document(documents, text: str, title: str = "lecture.txt"):
    digest = hashlib.sha256(title.encode()).hexdigest()
    return documents.create(Document(None, title, f"source-{title}", f"stored-{digest}.txt", "TXT", "text/plain", 1,
        digest, datetime.now(UTC), datetime.now(UTC),
        ExtractionStatus.EXTRACTED, text, metadata_json=json.dumps({"original_filename": title})))


def services(tmp_path):
    database = Database(tmp_path / "app.sqlite3"); connection = database.connect(); migrate(connection)
    documents, chunks, embedding, llm = DocumentRepository(connection), DocumentChunkRepository(connection), FakeEmbedding(), FakeLlm()
    return database, documents, chunks, embedding, llm


def test_chunker_handles_empty_japanese_newlines_and_overlap():
    chunker = DocumentChunker(max_characters=100, overlap_characters=20)
    assert chunker.chunk("  \n") == []
    chunks = chunker.chunk("第1段落です。\n\n第2段落です。\n第3段落です。")
    assert "第1段落" in chunks[0].text and len(chunks) == 1
    long = chunker.chunk("あ" * 190)
    assert len(long) == 2 and long[0].text[-20:] == long[1].text[:20]


def test_indexing_reindex_cleanup_and_document_delete_cascade(tmp_path):
    database, documents, chunks, embedding, _llm = services(tmp_path)
    document = make_document(documents, "電子回路1 Report Deadline 9/30")
    service = DocumentIndexingService(documents, chunks, embedding, DocumentChunker(max_characters=100, overlap_characters=10))
    indexed = service.index_document(document.id or 0)
    assert indexed.indexed and indexed.chunk_count == 1 and chunks.list_for_document(document.id or 0)
    duplicate = service.index_document(document.id or 0)
    assert duplicate.skipped and len(chunks.list_for_document(document.id or 0)) == 1
    reindexed = service.index_document(document.id or 0, force=True)
    assert reindexed.indexed and len(chunks.list_for_document(document.id or 0)) == 1
    assert documents.delete(document.id or 0) and chunks.list_for_document(document.id or 0) == []
    database.stop()


def test_indexing_skips_empty_and_preserves_old_index_on_embedding_failure(tmp_path):
    database, documents, chunks, embedding, _llm = services(tmp_path)
    empty = make_document(documents, "", "empty.txt")
    service = DocumentIndexingService(documents, chunks, embedding)
    assert service.index_document(empty.id or 0).skipped
    document = make_document(documents, "Report Deadline 9/30")
    assert service.index_document(document.id or 0).indexed
    embedding.fail = True
    failed = service.index_document(document.id or 0, force=True)
    assert failed.error and len(chunks.list_for_document(document.id or 0)) == 1
    database.stop()


def test_retriever_preserves_metadata_orders_scores_and_persists(tmp_path):
    database, documents, chunks, embedding, _llm = services(tmp_path)
    first = make_document(documents, "deadline", "report.txt")
    second = make_document(documents, "unrelated", "other.txt")
    now = datetime.now(UTC)
    chunks.replace_for_document(first.id or 0, [DocumentChunk(None, first.id or 0, 0, "Report Deadline 9/30", (1.0, 0.0), embedding.model, embedding.runtime, now, metadata_json='{"source_filename":"report.txt","source_type":"DOCUMENT"}')])
    chunks.replace_for_document(second.id or 0, [DocumentChunk(None, second.id or 0, 0, "other topic", (0.0, 1.0), embedding.model, embedding.runtime, now, metadata_json='{"source_filename":"other.txt","source_type":"DOCUMENT"}')])
    retrieved = Retriever(chunks, documents, embedding, top_k=1).retrieve("期限")
    assert len(retrieved) == 1 and retrieved[0].source_name == "report.txt" and retrieved[0].score == 1.0
    database.stop(); reopened = Database(tmp_path / "app.sqlite3"); connection = reopened.connect(); migrate(connection)
    assert len(DocumentChunkRepository(connection).list_for_document(first.id or 0)) == 1
    reopened.stop()


def test_rag_service_constructs_context_metadata_sources_and_abstains(tmp_path):
    database, documents, chunks, embedding, llm = services(tmp_path)
    document = make_document(documents, "deadline")
    now = datetime.now(UTC)
    chunks.replace_for_document(document.id or 0, [DocumentChunk(None, document.id or 0, 0, "Report Deadline 9/30", (1.0, 0.0), embedding.model, embedding.runtime, now, metadata_json='{"source_filename":"report.txt","source_type":"DOCUMENT"}')])
    rag = RagService(Retriever(chunks, documents, embedding), llm, score_threshold=.5)
    answer = rag.answer("期限")
    assert answer.answer == "資料に基づく回答" and answer.sources[0].filename == "report.txt" and "Report Deadline" in llm.calls[0][0]
    unknown = rag.answer("存在しない質問")
    assert unknown.abstained and not unknown.sources and len(llm.calls) == 1
    llm.fail = True
    try: rag.answer("期限")
    except RuntimeError: pass
    else: raise AssertionError("LLM failure must be surfaced to the worker boundary")
    database.stop()
