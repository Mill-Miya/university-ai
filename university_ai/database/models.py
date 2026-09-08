from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AssignmentStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class OverrideType(StrEnum):
    CANCEL = "CANCEL"
    MAKEUP = "MAKEUP"
    CHANGE = "CHANGE"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"


class ExtractionStatus(StrEnum):
    PENDING = "PENDING"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"


class CaptureType(StrEnum):
    FULL_SCREEN = "FULL_SCREEN"
    ACTIVE_WINDOW = "ACTIVE_WINDOW"
    REGION = "REGION"


@dataclass(frozen=True)
class Course:
    id: int | None
    name: str
    weekday: int
    start_time: str
    end_time: str
    timezone: str
    instructor: str | None = None
    classroom: str | None = None
    semester: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Assignment:
    id: int | None
    course_id: int
    title: str
    due_at: datetime
    status: AssignmentStatus = AssignmentStatus.TODO
    priority: str | None = None
    description: str | None = None
    source_document_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Exam:
    id: int | None
    course_id: int
    title: str
    start_at: datetime
    classroom: str | None = None
    scope: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ScheduleOverride:
    id: int | None
    course_id: int
    date: str
    type: OverrideType
    start_time: str | None = None
    end_time: str | None = None
    classroom: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class NotificationEvent:
    id: int | None
    rule_key: str
    subject_type: str
    subject_id: int
    scheduled_at: datetime
    status: NotificationStatus = NotificationStatus.PENDING
    delivered_at: datetime | None = None


@dataclass(frozen=True)
class Document:
    id: int | None
    title: str
    source_path: str
    stored_path: str
    file_type: str
    mime_type: str
    size_bytes: int
    sha256: str
    imported_at: datetime
    modified_at: datetime
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    extracted_text: str | None = None
    extraction_error: str | None = None
    metadata_json: str = "{}"


@dataclass(frozen=True)
class ScreenCapture:
    id: int | None
    capture_type: CaptureType
    stored_path: str
    width: int
    height: int
    captured_at: datetime
    monitor_index: int | None = None
    window_title: str | None = None
    metadata_json: str = "{}"
