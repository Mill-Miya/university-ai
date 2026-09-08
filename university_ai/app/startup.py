from __future__ import annotations

import os
import sys
import logging
from pathlib import Path


class WindowsStartupAdapter:
    """Per-user Startup-folder registration; no administrative permission is required."""

    def __init__(self, *, startup_directory: Path | None = None, filename: str = "University AI.cmd") -> None:
        default = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        self._directory = startup_directory or default
        self._path = self._directory / filename
        self._logger = logging.getLogger(__name__)

    def enabled(self) -> bool:
        return self._path.is_file()

    def enable(self) -> bool:
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            command = f'@echo off\r\n"{sys.executable}" -m university_ai.app.main\r\n'
            self._path.write_text(command, encoding="utf-8")
            return True
        except OSError:
            self._logger.exception("Startup registration failed")
            return False

    def disable(self) -> bool:
        try:
            self._path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            self._logger.exception("Startup removal failed")
            return False
        return True
