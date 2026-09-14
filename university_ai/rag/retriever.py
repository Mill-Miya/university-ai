from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: int
    chunk_id: int
    chunk_index: int
    text: str
    score: float
    source_name: str
    source_type: str
    page: int | None = None


class Retriever:
    def __init__(self, chunks, documents, embedding_engine, *, top_k: int = 4) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self._chunks, self._documents, self._embedding, self._top_k = chunks, documents, embedding_engine, top_k

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        if not query.strip(): return []
        query_vector = self._embedding.embed([query])[0]
        candidates: list[RetrievedChunk] = []
        for chunk in self._chunks.list_for_embedding_model(self._embedding.model):
            score = self._cosine(query_vector, chunk.embedding)
            if score is None: continue
            document = self._documents.get(chunk.document_id)
            if document is None: continue
            metadata = json.loads(chunk.metadata_json)
            candidates.append(RetrievedChunk(chunk.document_id, chunk.id or 0, chunk.chunk_index, chunk.text, score,
                str(metadata.get("source_filename", document.title)), str(metadata.get("source_type", "DOCUMENT")), chunk.page))
        return sorted(candidates, key=lambda item: item.score, reverse=True)[:top_k or self._top_k]

    @staticmethod
    def _cosine(left: tuple[float, ...] | list[float], right: tuple[float, ...]) -> float | None:
        if len(left) != len(right) or not left: return None
        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
        return None if denominator == 0 else sum(a * b for a, b in zip(left, right, strict=True)) / denominator
