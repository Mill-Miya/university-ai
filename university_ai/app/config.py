from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Filesystem configuration; no secrets or external endpoints are stored here."""

    data_dir: Path
    log_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "university_ai.sqlite3"

    @classmethod
    def default(cls, root: Path | None = None) -> "AppConfig":
        base = root or Path.cwd()
        return cls(data_dir=base / "data", log_dir=base / "logs")

