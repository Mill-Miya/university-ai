from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from university_ai.database.models import Assignment, AssignmentStatus, Course, Exam, OverrideType, ScheduleOverride


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _validate_time(value: str) -> None:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as error:
        raise ValueError("time must use HH:MM format") from error


def _validate_course(course: Course) -> None:
    if not 0 <= course.weekday <= 6:
        raise ValueError("weekday must be between 0 and 6")
    _validate_time(course.start_time)
    _validate_time(course.end_time)
    if course.start_time >= course.end_time:
        raise ValueError("end_time must be later than start_time")
    try:
        ZoneInfo(course.timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("timezone must be an IANA timezone") from error


def _validate_override(override: ScheduleOverride) -> None:
    try:
        datetime.strptime(override.date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("date must use YYYY-MM-DD format") from error
    if override.type in (OverrideType.MAKEUP, OverrideType.CHANGE):
        if not override.start_time or not override.end_time:
            raise ValueError("MAKEUP and CHANGE require start_time and end_time")
        _validate_time(override.start_time)
        _validate_time(override.end_time)
        if override.start_time >= override.end_time:
            raise ValueError("end_time must be later than start_time")


class CourseRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    def create(self, course: Course) -> Course:
        _validate_course(course)
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

    def update(self, course: Course) -> Course:
        if course.id is None:
            raise ValueError("course id is required for update")
        _validate_course(course)
        cursor = self._db.execute(
            """UPDATE courses SET name=?,instructor=?,classroom=?,weekday=?,start_time=?,end_time=?,timezone=?,semester=?,notes=?
            WHERE id=?""",
            (course.name, course.instructor, course.classroom, course.weekday, course.start_time, course.end_time,
             course.timezone, course.semester, course.notes, course.id),
        )
        self._db.commit()
        if cursor.rowcount != 1:
            raise KeyError(f"course {course.id} not found")
        return course

    def delete(self, course_id: int) -> bool:
        cursor = self._db.execute("DELETE FROM courses WHERE id=?", (course_id,))
        self._db.commit()
        return cursor.rowcount == 1


class AssignmentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    def create(self, assignment: Assignment) -> Assignment:
        now = datetime.now(UTC)
        created, updated = assignment.created_at or now, assignment.updated_at or now
        cursor = self._db.execute("""INSERT INTO assignments(course_id,title,description,due_at,status,priority,source_document_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""", (assignment.course_id, assignment.title, assignment.description, _utc_text(assignment.due_at),
            assignment.status.value, assignment.priority, assignment.source_document_id, _utc_text(created), _utc_text(updated)))
        self._db.commit()
        return replace(assignment, id=cursor.lastrowid, created_at=created, updated_at=updated)

    def get(self, assignment_id: int) -> Assignment | None:
        row = self._db.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
        return _assignment(row) if row else None

    def list(self, *, include_finished: bool = True) -> list[Assignment]:
        sql = "SELECT * FROM assignments"
        parameters: tuple[str, ...] = ()
        if not include_finished:
            sql += " WHERE status NOT IN (?, ?)"
            parameters = (AssignmentStatus.DONE.value, AssignmentStatus.CANCELLED.value)
        return [_assignment(row) for row in self._db.execute(sql + " ORDER BY due_at", parameters)]

    def update(self, assignment: Assignment) -> Assignment:
        if assignment.id is None:
            raise ValueError("assignment id is required for update")
        updated = datetime.now(UTC)
        cursor = self._db.execute(
            """UPDATE assignments SET course_id=?,title=?,description=?,due_at=?,status=?,priority=?,source_document_id=?,updated_at=?
            WHERE id=?""",
            (assignment.course_id, assignment.title, assignment.description, _utc_text(assignment.due_at), assignment.status.value,
             assignment.priority, assignment.source_document_id, _utc_text(updated), assignment.id),
        )
        self._db.commit()
        if cursor.rowcount != 1:
            raise KeyError(f"assignment {assignment.id} not found")
        return replace(assignment, updated_at=updated)

    def delete(self, assignment_id: int) -> bool:
        cursor = self._db.execute("DELETE FROM assignments WHERE id=?", (assignment_id,))
        self._db.commit()
        return cursor.rowcount == 1


class ExamRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    def create(self, exam: Exam) -> Exam:
        cursor = self._db.execute("INSERT INTO exams(course_id,title,start_at,classroom,scope,notes) VALUES (?,?,?,?,?,?)",
            (exam.course_id, exam.title, _utc_text(exam.start_at), exam.classroom, exam.scope, exam.notes))
        self._db.commit()
        return replace(exam, id=cursor.lastrowid)

    def get(self, exam_id: int) -> Exam | None:
        row = self._db.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
        return _exam(row) if row else None

    def list(self) -> list[Exam]:
        return [_exam(row) for row in self._db.execute("SELECT * FROM exams ORDER BY start_at")]

    def update(self, exam: Exam) -> Exam:
        if exam.id is None:
            raise ValueError("exam id is required for update")
        cursor = self._db.execute(
            "UPDATE exams SET course_id=?,title=?,start_at=?,classroom=?,scope=?,notes=? WHERE id=?",
            (exam.course_id, exam.title, _utc_text(exam.start_at), exam.classroom, exam.scope, exam.notes, exam.id),
        )
        self._db.commit()
        if cursor.rowcount != 1:
            raise KeyError(f"exam {exam.id} not found")
        return exam

    def delete(self, exam_id: int) -> bool:
        cursor = self._db.execute("DELETE FROM exams WHERE id=?", (exam_id,))
        self._db.commit()
        return cursor.rowcount == 1


class ScheduleOverrideRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    def create(self, override: ScheduleOverride) -> ScheduleOverride:
        _validate_override(override)
        cursor = self._db.execute("""INSERT INTO schedule_overrides(course_id,date,type,start_time,end_time,classroom,notes)
            VALUES (?,?,?,?,?,?,?)""", (override.course_id, override.date, override.type.value, override.start_time,
            override.end_time, override.classroom, override.notes))
        self._db.commit()
        return replace(override, id=cursor.lastrowid)

    def get(self, override_id: int) -> ScheduleOverride | None:
        row = self._db.execute("SELECT * FROM schedule_overrides WHERE id=?", (override_id,)).fetchone()
        return _override(row) if row else None

    def list_for_course(self, course_id: int) -> list[ScheduleOverride]:
        rows = self._db.execute("SELECT * FROM schedule_overrides WHERE course_id=? ORDER BY date", (course_id,))
        return [_override(row) for row in rows]

    def update(self, override: ScheduleOverride) -> ScheduleOverride:
        if override.id is None:
            raise ValueError("override id is required for update")
        _validate_override(override)
        cursor = self._db.execute(
            """UPDATE schedule_overrides SET course_id=?,date=?,type=?,start_time=?,end_time=?,classroom=?,notes=?
            WHERE id=?""",
            (override.course_id, override.date, override.type.value, override.start_time, override.end_time,
             override.classroom, override.notes, override.id),
        )
        self._db.commit()
        if cursor.rowcount != 1:
            raise KeyError(f"schedule override {override.id} not found")
        return override

    def delete(self, override_id: int) -> bool:
        cursor = self._db.execute("DELETE FROM schedule_overrides WHERE id=?", (override_id,))
        self._db.commit()
        return cursor.rowcount == 1


def _course(row: sqlite3.Row) -> Course:
    return Course(**dict(row))


def _assignment(row: sqlite3.Row) -> Assignment:
    values = dict(row)
    values["due_at"] = _as_utc(values["due_at"])
    values["created_at"] = _as_utc(values["created_at"])
    values["updated_at"] = _as_utc(values["updated_at"])
    values["status"] = AssignmentStatus(values["status"])
    return Assignment(**values)


def _exam(row: sqlite3.Row) -> Exam:
    values = dict(row)
    values["start_at"] = _as_utc(values["start_at"])
    return Exam(**values)


def _override(row: sqlite3.Row) -> ScheduleOverride:
    values = dict(row)
    values["type"] = OverrideType(values["type"])
    return ScheduleOverride(**values)
