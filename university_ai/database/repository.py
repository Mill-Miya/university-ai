from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

from university_ai.database.models import Assignment, AssignmentStatus, Course, Exam, OverrideType, ScheduleOverride


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class CourseRepository:
    def __init__(self, connection: sqlite3.Connection) -> None: self._db = connection

    def create(self, course: Course) -> Course:
        if not 0 <= course.weekday <= 6: raise ValueError("weekday must be between 0 and 6")
        cursor = self._db.execute("""INSERT INTO courses(name,instructor,classroom,weekday,start_time,end_time,timezone,semester,notes)
            VALUES (?,?,?,?,?,?,?,?,?)""", (course.name, course.instructor, course.classroom, course.weekday, course.start_time,
            course.end_time, course.timezone, course.semester, course.notes))
        self._db.commit()
        return replace(course, id=cursor.lastrowid)

    def get(self, course_id: int) -> Course | None:
        row = self._db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
        return _course(row) if row else None

    def list(self) -> list[Course]:
        return [_course(r) for r in self._db.execute("SELECT * FROM courses ORDER BY weekday,start_time")]


class AssignmentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None: self._db = connection

    def create(self, assignment: Assignment) -> Assignment:
        now = datetime.now(UTC)
        created, updated = assignment.created_at or now, assignment.updated_at or now
        cursor = self._db.execute("""INSERT INTO assignments(course_id,title,description,due_at,status,priority,source_document_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""", (assignment.course_id, assignment.title, assignment.description, _utc_text(assignment.due_at),
            assignment.status.value, assignment.priority, assignment.source_document_id, _utc_text(created), _utc_text(updated)))
        self._db.commit()
        return replace(assignment, id=cursor.lastrowid, created_at=created, updated_at=updated)


class ExamRepository:
    def __init__(self, connection: sqlite3.Connection) -> None: self._db = connection

    def create(self, exam: Exam) -> Exam:
        cursor = self._db.execute("INSERT INTO exams(course_id,title,start_at,classroom,scope,notes) VALUES (?,?,?,?,?,?)",
            (exam.course_id, exam.title, _utc_text(exam.start_at), exam.classroom, exam.scope, exam.notes))
        self._db.commit()
        return replace(exam, id=cursor.lastrowid)


class ScheduleOverrideRepository:
    def __init__(self, connection: sqlite3.Connection) -> None: self._db = connection

    def create(self, override: ScheduleOverride) -> ScheduleOverride:
        cursor = self._db.execute("""INSERT INTO schedule_overrides(course_id,date,type,start_time,end_time,classroom,notes)
            VALUES (?,?,?,?,?,?,?)""", (override.course_id, override.date, override.type.value, override.start_time,
            override.end_time, override.classroom, override.notes))
        self._db.commit()
        return replace(override, id=cursor.lastrowid)


def _course(row: sqlite3.Row) -> Course:
    return Course(**dict(row))
