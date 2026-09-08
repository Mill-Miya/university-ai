from __future__ import annotations

from collections.abc import Callable
from html import escape
import logging

from university_ai.core.rules import NotificationCandidate
from university_ai.notification.registration import APP_USER_MODEL_ID, WindowsToastRegistration


class WindowsToastAdapter:
    """Windows-specific adapter boundary. The UI layer injects the actual Toast sender."""

    def __init__(
        self,
        toast_sender: Callable[[str, str], None] | None = None,
        *,
        app_id: str = APP_USER_MODEL_ID,
        registration: WindowsToastRegistration | None = None,
    ) -> None:
        self._toast_sender = toast_sender
        self._app_id = app_id
        self._registration = registration or WindowsToastRegistration(app_id=app_id)
        self._logger = logging.getLogger(__name__)

    def send(self, candidate: NotificationCandidate) -> None:
        if self._toast_sender is not None:
            self._toast_sender(candidate.title, candidate.body)
            return
        if not self._registration.register():
            raise RuntimeError("Windows Toast identity registration is unavailable")
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
        try:
            setting = notifier.setting
        except OSError as error:
            # Some unpackaged WinRT hosts return ERROR_NOT_FOUND for this
            # diagnostic property even after the shortcut is registered.  It
            # does not mean the notification is blocked, so still let show()
            # report the authoritative send result.
            self._logger.warning("Windows Toast notifier setting is unavailable: %s", error)
        else:
            setting_name = getattr(setting, "name", str(setting))
            self._logger.info("Windows Toast notifier setting=%s app_id=%s", setting_name, self._app_id)
            if setting_name != "ENABLED":
                raise RuntimeError(f"Windows Toast is blocked: notifier setting={setting_name}")
        notifier.show(ToastNotification(document))
