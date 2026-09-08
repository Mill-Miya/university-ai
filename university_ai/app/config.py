from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Filesystem configuration; no secrets or external endpoints are stored here."""

    data_dir: Path
    log_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "university_ai.sqlite3"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    @classmethod
    def default(cls, root: Path | None = None) -> "AppConfig":
        base = root or Path.cwd()
        return cls(data_dir=base / "data", log_dir=base / "logs")


@dataclass(frozen=True)
class UserSettings:
    course_notifications: bool = True
    assignment_notifications: bool = True
    exam_notifications: bool = True
    course_minutes: int = 30
    assignment_minutes: int = 24 * 60
    exam_minutes: int = 24 * 60
    startup_enabled: bool = False


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> UserSettings:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return UserSettings(
                course_notifications=self._boolean(raw["course_notifications"]),
                assignment_notifications=self._boolean(raw["assignment_notifications"]),
                exam_notifications=self._boolean(raw["exam_notifications"]),
                course_minutes=self._minutes(raw["course_minutes"]),
                assignment_minutes=self._minutes(raw["assignment_minutes"]),
                exam_minutes=self._minutes(raw["exam_minutes"]),
                startup_enabled=self._boolean(raw["startup_enabled"]),
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return UserSettings()

    def save(self, settings: UserSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(settings.__dict__, indent=2), encoding="utf-8")

    @staticmethod
    def _minutes(value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("boolean is not a duration")
        minutes = int(value)
        if not 0 <= minutes <= 7 * 24 * 60:
            raise ValueError("notification duration out of range")
        return minutes

    @staticmethod
    def _boolean(value: object) -> bool:
        if not isinstance(value, bool):
            raise ValueError("boolean setting required")
        return value
