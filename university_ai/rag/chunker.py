from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str


class DocumentChunker:
    """Small deterministic paragraph/sentence-oriented chunker for local documents."""

    def __init__(self, *, max_characters: int = 800, overlap_characters: int = 120) -> None:
        if max_characters < 100 or not 0 <= overlap_characters < max_characters:
            raise ValueError("invalid chunk size or overlap")
        self._max = max_characters
        self._overlap = overlap_characters

    def chunk(self, text: str) -> list[TextChunk]:
        normalized = re.sub(r"\r\n?", "\n", text).strip()
        if not normalized:
            return []
        units = self._units(normalized)
        chunks: list[str] = []
        current = ""
        for unit in units:
            for piece in self._split_long_unit(unit):
                candidate = piece if not current else f"{current}\n{piece}"
                if len(candidate) <= self._max:
                    current = candidate
                    continue
                if current:
                    chunks.append(current.strip())
                    overlap = current[-self._overlap:].strip() if self._overlap else ""
                    current = f"{overlap}\n{piece}".strip() if overlap else piece
                else:
                    current = piece
        if current:
            chunks.append(current.strip())
        return [TextChunk(index=index, text=chunk) for index, chunk in enumerate(chunks) if chunk]

    @staticmethod
    def _units(text: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        units: list[str] = []
        for paragraph in paragraphs:
            units.extend(part.strip() for part in re.split(r"(?<=[。！？.!?])\s+|\n+", paragraph) if part.strip())
        return units or [text]

    def _split_long_unit(self, unit: str) -> list[str]:
        if len(unit) <= self._max:
            return [unit]
        # The caller applies overlap when it flushes a completed chunk. Splitting
        # here without overlap prevents duplicated overlap text in long paragraphs.
        return [unit[start:start + self._max] for start in range(0, len(unit), self._max)]
