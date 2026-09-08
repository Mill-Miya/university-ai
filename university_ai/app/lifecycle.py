from __future__ import annotations

import logging
from typing import Protocol


class Stoppable(Protocol):
    def stop(self) -> None: ...


class ApplicationLifecycle:
    """Coordinates safe shutdown without owning UI, database, or scheduler details."""

    def __init__(self, *stoppables: Stoppable) -> None:
        self._stoppables = stoppables
        self._logger = logging.getLogger(__name__)

    def stop(self) -> None:
        self._logger.info("Application lifecycle stopping")
        for component in reversed(self._stoppables):
            try:
                component.stop()
            except Exception:
                self._logger.exception("Component shutdown failed")
        self._logger.info("Application lifecycle stopped")
