from __future__ import annotations

from pathlib import Path


class TextExtractor:
    def extract(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="strict")


class PdfTextExtractor:
    def extract(self, path: Path) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


class DocxTextExtractor:
    def extract(self, path: Path) -> str:
        from docx import Document as DocxDocument

        return "\n".join(paragraph.text for paragraph in DocxDocument(str(path)).paragraphs).strip()


def extractor_for(file_type: str) -> TextExtractor | PdfTextExtractor | DocxTextExtractor | None:
    return {
        "TXT": TextExtractor(),
        "PDF": PdfTextExtractor(),
        "DOCX": DocxTextExtractor(),
    }.get(file_type)
