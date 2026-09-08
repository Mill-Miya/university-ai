from __future__ import annotations

import sqlite3


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, """
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            instructor TEXT, classroom TEXT,
            weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            start_time TEXT NOT NULL, end_time TEXT NOT NULL,
            timezone TEXT NOT NULL, semester TEXT, notes TEXT
        );
        CREATE TABLE assignments (
            id INTEGER PRIMARY KEY,
            course_id INTEGER NOT NULL REFERENCES courses(id),
            title TEXT NOT NULL, description TEXT, due_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('TODO','IN_PROGRESS','DONE','CANCELLED')),
            priority TEXT, source_document_id INTEGER,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE exams (
            id INTEGER PRIMARY KEY,
            course_id INTEGER NOT NULL REFERENCES courses(id),
            title TEXT NOT NULL, start_at TEXT NOT NULL,
            classroom TEXT, scope TEXT, notes TEXT
        );
        CREATE TABLE schedule_overrides (
            id INTEGER PRIMARY KEY,
            course_id INTEGER NOT NULL REFERENCES courses(id),
            date TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('CANCEL','MAKEUP','CHANGE')),
            start_time TEXT, end_time TEXT, classroom TEXT, notes TEXT
        );
        CREATE UNIQUE INDEX schedule_overrides_course_date_type
            ON schedule_overrides(course_id, date, type);
    """),
)


def migrate(connection: sqlite3.Connection) -> None:
    """Apply each version atomically; a failed version is fully rolled back."""
    connection.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    current = int(row[0]) if row else 0
    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        try:
            connection.execute("BEGIN")
            connection.executescript(sql)
            connection.execute("DELETE FROM schema_version")
            connection.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

