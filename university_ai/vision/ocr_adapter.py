from __future__ import annotations

import os
import tempfile
from pathlib import Path

from university_ai.llm.models import ImageInput


class TemporaryOcrAdapter:
    """Uses a short-lived local file only because Tesseract accepts paths."""

    def __init__(self, engine) -> None:
        self._engine = engine

    def recognize(self, image: ImageInput, *, language: str = "jpn+eng"):
        suffix = ".png" if image.mime_type == "image/png" else ".jpg"
        descriptor, filename = tempfile.mkstemp(prefix="university_ai_vision_", suffix=suffix)
        path = Path(filename)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(image.data)
            return self._engine.recognize_image(path, language=language)
        finally:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
