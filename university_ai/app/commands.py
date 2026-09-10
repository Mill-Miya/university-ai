"""Fixed application actions shared by Tray and the authenticated Core bridge."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot


class ApplicationCommand(str, Enum):
    ASK_AI = "ask_ai"
    ASK_REGION = "ask_region"
    OPEN_DOCUMENTS = "open_documents"
    OPEN_SETTINGS = "open_settings"


class CommandUnavailable(Exception):
    pass


class CommandBusy(Exception):
    pass


@dataclass(frozen=True)
class CommandIntent:
    command: ApplicationCommand
    connected: threading.Event
    deadline: float
    respond: Callable[[str | None], None]


class ApplicationCommandDispatcher(QObject):
    requested = Signal(object)

    def __init__(self, handlers, parent=None):
        super().__init__(parent)
        self.handlers = dict(handlers)
        self._stopped = False
        self._busy = False
        self._last = -float("inf")
        self._queue_lock = threading.Lock()
        self._queued = False
        self.requested.connect(self._receive, Qt.ConnectionType.QueuedConnection)

    @property
    def commands(self):
        return [command.value for command in self.handlers]

    def submit(self, intent):
        with self._queue_lock:
            if self._queued:
                intent.respond('busy')
                return
            self._queued = True
        self.requested.emit(intent)

    @Slot(object)
    def _receive(self, intent):
        with self._queue_lock:
            self._queued = False
        # A disconnected or expired intent must never survive into a new session.
        if not intent.connected.is_set() or time.monotonic() > intent.deadline:
            return
        intent.respond(self.invoke(intent.command))

    def invoke(self, command):
        if self._stopped:
            return "unavailable"
        if not isinstance(command, ApplicationCommand) or command not in self.handlers:
            return "invalid"
        now = time.monotonic()
        if self._busy or now - self._last < 0.4:
            return "busy"
        self._busy, self._last = True, now
        try:
            self.handlers[command]()
            return None
        except CommandUnavailable:
            return "unavailable"
        except CommandBusy:
            return "busy"
        except Exception:
            logging.getLogger(__name__).warning("Application command failed: %s", command.value)
            return "failed"
        finally:
            self._busy = False

    def stop(self):
        self._stopped = True
