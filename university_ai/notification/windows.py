from __future__ import annotations

from collections.abc import Callable

from university_ai.core.rules import NotificationCandidate


class WindowsToastAdapter:
    """Windows-specific adapter boundary. The UI layer injects the actual Toast sender."""

    def __init__(self, toast_sender: Callable[[str, str], None] | None = None) -> None:
        self._toast_sender = toast_sender

    def send(self, candidate: NotificationCandidate) -> None:
        if self._toast_sender is None:
            raise RuntimeError("Windows Toast is unavailable")
        self._toast_sender(candidate.title, candidate.body)
