from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # APScheduler evaluates rules on a background thread. SQLite's serialized
            # runtime permits this shared connection; busy_timeout avoids immediate
            # failure if the UI and scheduler touch the local DB at the same time.
            self._connection = sqlite3.connect(self._path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
        return self._connection

    def stop(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
