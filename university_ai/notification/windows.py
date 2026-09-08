from __future__ import annotations

from collections.abc import Callable
from html import escape

from university_ai.core.rules import NotificationCandidate


class WindowsToastAdapter:
    """Windows-specific adapter boundary. The UI layer injects the actual Toast sender."""

    def __init__(self, toast_sender: Callable[[str, str], None] | None = None, *, app_id: str = "UniversityAI") -> None:
        self._toast_sender = toast_sender
        self._app_id = app_id

    def send(self, candidate: NotificationCandidate) -> None:
        if self._toast_sender is not None:
            self._toast_sender(candidate.title, candidate.body)
            return
        try:
            from winrt.windows.data.xml.dom import XmlDocument
            from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager
        except ImportError as error:
            raise RuntimeError("Windows Toast runtime is unavailable") from error
        document = XmlDocument()
        document.load_xml(
            f"<toast><visual><binding template='ToastGeneric'><text>{escape(candidate.title)}</text>"
            f"<text>{escape(candidate.body)}</text></binding></visual></toast>"
        )
        notifier = ToastNotificationManager.create_toast_notifier_with_id(self._app_id)
        notifier.show(ToastNotification(document))
