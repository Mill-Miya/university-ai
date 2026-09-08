from __future__ import annotations

from collections.abc import Callable

from university_ai.core.rules import NotificationCandidate


class TrayFallbackAdapter:
    """Fallback boundary, intended for a PySide6 system-tray message sender in Phase 6."""

    def __init__(self, message_sender: Callable[[str, str], None] | None = None) -> None:
        self._message_sender = message_sender

    def send(self, candidate: NotificationCandidate) -> None:
        if self._message_sender is None:
            raise RuntimeError("Tray fallback is unavailable")
        self._message_sender(candidate.title, candidate.body)


class FallbackOnErrorAdapter:
    """Uses fallback only when the primary adapter cannot deliver a notification."""

    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def send(self, candidate: NotificationCandidate) -> None:
        try:
            self._primary.send(candidate)
        except Exception:
            self._fallback.send(candidate)
