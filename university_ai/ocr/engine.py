from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class OcrEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecognizedText:
    text: str
    language: str
    engine: str
    metadata_json: str = "{}"


class TesseractOcrEngine:
    """Local Tesseract adapter. No image bytes ever leave the PC."""

    engine_name = "tesseract"

    def __init__(self, executable: str | None = None, *, timeout_seconds: int = 60) -> None:
        self._executable = executable or self._find_executable()
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _find_executable() -> str | None:
        discovered = shutil.which("tesseract")
        if discovered:
            return discovered
        for location in (Path("C:/Program Files/Tesseract-OCR/tesseract.exe"), Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe")):
            if location.is_file():
                return str(location)
        return None

    def availability(self) -> bool:
        return self._executable is not None

    def supported_languages(self) -> tuple[str, ...]:
        if not self._executable:
            return ()
        completed = self._run([self._executable, "--list-langs"])
        return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip() and not line.startswith("List of"))

    def recognize_image(self, path: Path, *, language: str = "jpn+eng") -> RecognizedText:
        if not path.is_file():
            raise OcrEngineError("OCR image file is missing")
        if not self._executable:
            raise OcrEngineError("Local Tesseract OCR is unavailable")
        available = set(self.supported_languages())
        required = set(language.split("+"))
        if not required.issubset(available):
            raise OcrEngineError(f"OCR language data is unavailable: {language}")
        completed = self._run([self._executable, str(path), "stdout", "-l", language])
        return RecognizedText(completed.stdout.strip(), language, self.engine_name,
                              json.dumps({"engine_version": self._version()}))

    def _version(self) -> str:
        if not self._executable:
            return "unavailable"
        return self._run([self._executable, "--version"]).stdout.splitlines()[0].strip()

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=self._timeout_seconds, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            raise OcrEngineError("Local Tesseract OCR failed") from error
