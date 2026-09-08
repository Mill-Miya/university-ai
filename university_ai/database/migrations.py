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
    (2, """
        CREATE TABLE notification_events (
            id INTEGER PRIMARY KEY,
            rule_key TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            scheduled_at TEXT NOT NULL,
            delivered_at TEXT,
            status TEXT NOT NULL CHECK (status IN ('PENDING','DELIVERED','FAILED','SUPPRESSED')),
            UNIQUE(rule_key, subject_type, subject_id, scheduled_at)
        );
    """),
    (3, """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            source_path TEXT NOT NULL,
            stored_path TEXT NOT NULL UNIQUE,
            file_type TEXT NOT NULL CHECK (file_type IN ('PDF','TXT','DOCX','PNG','JPG','JPEG')),
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            sha256 TEXT NOT NULL UNIQUE,
            imported_at TEXT NOT NULL,
            modified_at TEXT NOT NULL,
            extraction_status TEXT NOT NULL CHECK (extraction_status IN ('PENDING','EXTRACTED','FAILED')),
            extracted_text TEXT,
            extraction_error TEXT,
            metadata_json TEXT NOT NULL
        );
    """),
    (4, """
        CREATE TABLE screen_captures (
            id INTEGER PRIMARY KEY,
            capture_type TEXT NOT NULL CHECK (capture_type IN ('FULL_SCREEN','ACTIVE_WINDOW','REGION')),
            stored_path TEXT NOT NULL UNIQUE,
            width INTEGER NOT NULL CHECK (width > 0),
            height INTEGER NOT NULL CHECK (height > 0),
            monitor_index INTEGER,
            window_title TEXT,
            captured_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );
    """),
    (5, """
        CREATE TABLE ocr_results (
            id INTEGER PRIMARY KEY,
            source_type TEXT NOT NULL CHECK (source_type IN ('DOCUMENT','SCREEN_CAPTURE')),
            source_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING','EXTRACTED','FAILED')),
            text TEXT,
            language TEXT,
            engine TEXT,
            processed_at TEXT NOT NULL,
            error TEXT,
            metadata_json TEXT NOT NULL
        );
        CREATE INDEX ocr_results_source_processed
            ON ocr_results(source_type, source_id, processed_at DESC);
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
