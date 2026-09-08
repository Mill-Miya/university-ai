from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from university_ai.capture.backend import CaptureRectangle, CapturedFrame
from university_ai.database.models import ScreenCapture
from university_ai.database.repository import ScreenCaptureRepository


class CaptureStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaptureResult:
    capture: ScreenCapture


class CaptureStorageService:
    """PNG file storage. Repository deletion deliberately never deletes files."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def store_png(self, image: object, captured_at: datetime) -> Path:
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("Timezone-aware datetime required")
        destination = self._directory / f"{captured_at:%Y}" / f"{captured_at:%m}" / f"{uuid4().hex}.png"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not image.save(str(destination), "PNG"):
                raise CaptureStorageError("image could not be saved as PNG")
        except (OSError, CaptureStorageError) as error:
            try:
                self.delete_file(destination)
            except OSError:
                pass
            raise CaptureStorageError("capture image could not be stored") from error
        return destination

    @staticmethod
    def delete_file(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return


class ScreenCaptureService:
    """Application service: capture once, store a PNG, then persist metadata."""

    def __init__(self, backend, repository: ScreenCaptureRepository, storage: CaptureStorageService) -> None:
        self._backend = backend
        self._repository = repository
        self._storage = storage
        self._logger = logging.getLogger(__name__)

    def capture_full_screen(self) -> CaptureResult:
        return self._capture(self._backend.capture_full_screen())

    def snapshot_active_window(self) -> int | None:
        return self._backend.snapshot_active_window()

    def capture_active_window(self, preferred_hwnd: int | None = None) -> CaptureResult:
        return self._capture(self._backend.capture_active_window(preferred_hwnd))

    def capture_region(self, rectangle: CaptureRectangle) -> CaptureResult:
        rectangle.validate()
        return self._capture(self._backend.capture_region(rectangle))

    def _capture(self, frame: CapturedFrame) -> CaptureResult:
        captured_at = datetime.now(UTC)
        path = self._storage.store_png(frame.image, captured_at)
        try:
            capture = ScreenCapture(
                id=None,
                capture_type=frame.capture_type,
                stored_path=str(path.resolve()),
                width=frame.image.toImage().width(),
                height=frame.image.toImage().height(),
                monitor_index=frame.monitor_index,
                window_title=frame.window_title,
                captured_at=captured_at,
                metadata_json=frame.metadata_json,
            )
            stored = self._repository.create(capture)
        except Exception:
            self._logger.exception("Screen capture metadata persistence failed; removing stored image")
            try:
                self._storage.delete_file(path)
            except OSError:
                self._logger.exception("Screen capture cleanup failed")
            raise
        self._logger.info("Screen capture saved at %s", path)
        return CaptureResult(stored)

    def delete(self, capture_id: int) -> bool:
        """Service-level deletion removes PNG first, then its metadata record.

        A direct repository delete intentionally removes only metadata. File and
        database operations cannot be atomic, so callers receive errors for any
        partial cleanup and can retry safely.
        """
        capture = self._repository.get(capture_id)
        if capture is None:
            return False
        self._storage.delete_file(Path(capture.stored_path))
        return self._repository.delete_metadata(capture_id)
