from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from university_ai.core.context import ContextEngine
from university_ai.core.rules import NotificationCandidate, RuleEngine


class UniversityScheduler:
    """APScheduler adapter that forwards Rule Engine candidates without delivering notifications."""

    def __init__(
        self,
        context_engine: ContextEngine,
        rule_engine: RuleEngine,
        candidate_consumer: Callable[[list[NotificationCandidate]], None],
        *,
        interval_seconds: int = 60,
    ) -> None:
        self._context_engine = context_engine
        self._rule_engine = rule_engine
        self._candidate_consumer = candidate_consumer
        self._interval_seconds = interval_seconds
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._logger = logging.getLogger(__name__)

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        if self.running:
            return
        self._scheduler.add_job(self.run_once, "interval", seconds=self._interval_seconds, id="rule_evaluation", replace_existing=True)
        self._scheduler.start()

    def run_once(self) -> None:
        try:
            context = self._context_engine.build(datetime.now(UTC))
            self._candidate_consumer(self._rule_engine.evaluate(context))
        except Exception:
            self._logger.exception("Scheduled rule evaluation failed")

    def stop(self) -> None:
        if self.running:
            self._scheduler.shutdown(wait=False)
