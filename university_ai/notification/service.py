from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from university_ai.core.rules import NotificationCandidate
from university_ai.database.models import NotificationEvent, NotificationStatus
from university_ai.database.repository import NotificationEventRepository


class NotificationAdapter(Protocol):
    def send(self, candidate: NotificationCandidate) -> None: ...


class NotificationService:
    """Converts candidates to durable events, then delegates delivery to an adapter."""

    def __init__(self, events: NotificationEventRepository, adapter: NotificationAdapter) -> None:
        self._events = events
        self._adapter = adapter
        self._logger = logging.getLogger(__name__)

    def __call__(self, candidates: list[NotificationCandidate]) -> None:
        self.process(candidates)

    def process(
        self,
        candidates: list[NotificationCandidate],
        *,
        should_deliver: Callable[[NotificationCandidate], bool] | None = None,
    ) -> list[NotificationEvent]:
        results: list[NotificationEvent] = []
        for candidate in candidates:
            try:
                event, created = self._events.create_if_absent(NotificationEvent(
                    None, candidate.rule_key, candidate.subject_type, candidate.subject_id, candidate.scheduled_at
                ))
            except (sqlite3.Error, ValueError):
                self._logger.exception("Notification event persistence failed")
                continue
            if not created:
                results.append(event)
                continue
            if should_deliver is not None and not should_deliver(candidate):
                results.append(self._events.update_status(event.id, NotificationStatus.SUPPRESSED))
                continue
            try:
                self._adapter.send(candidate)
            except Exception:
                self._logger.exception("Notification delivery failed")
                results.append(self._events.update_status(event.id, NotificationStatus.FAILED))
            else:
                results.append(self._events.update_status(event.id, NotificationStatus.DELIVERED, delivered_at=datetime.now(UTC)))
        return results
