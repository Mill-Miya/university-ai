from __future__ import annotations

import time
from dataclasses import dataclass

from university_ai.rag.retriever import RetrievedChunk


@dataclass(frozen=True)
class RagSource:
    filename: str
    document_id: int
    chunk_index: int
    score: float
    page: int | None = None


@dataclass(frozen=True)
class RagResponse:
    answer: str
    chunks: tuple[RetrievedChunk, ...]
    sources: tuple[RagSource, ...]
    model: str | None
    duration_seconds: float
    metadata: dict[str, object]
    abstained: bool = False


class RagService:
    _ABSTENTION = "取り込まれた資料から十分な根拠を見つけられませんでした。"
    _INSTRUCTION = "提供された資料抜粋だけを根拠に日本語で簡潔かつ正確に回答してください。資料にない事実は断定せず、OCR誤認識の可能性にも注意してください。"
    def __init__(self, retriever, llm_service, *, score_threshold: float = 0.45) -> None:
        self._retriever, self._llm, self._threshold = retriever, llm_service, score_threshold

    def answer(self, question: str) -> RagResponse:
        started = time.monotonic(); chunks = tuple(self._retriever.retrieve(question))
        if not chunks or chunks[0].score < self._threshold:
            return RagResponse(self._ABSTENTION, chunks, (), None, time.monotonic() - started,
                               {"reason": "insufficient_retrieval", "threshold": self._threshold}, True)
        sources = tuple(RagSource(chunk.source_name, chunk.document_id, chunk.chunk_index, chunk.score, chunk.page) for chunk in chunks)
        context = "\n\n".join(f"[資料: {chunk.source_name} / chunk {chunk.chunk_index}]\n{chunk.text}" for chunk in chunks)
        response = self._llm.ask(f"資料抜粋:\n{context}\n\n質問: {question}", system_prompt=self._INSTRUCTION)
        return RagResponse(response.text, chunks, sources, response.model, time.monotonic() - started, response.metadata)
