from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PresenceEventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class PresenceSource(str, Enum):
    FACE = "FACE"
    MANUAL = "MANUAL"


class PresenceStatus(str, Enum):
    VALID = "VALID"
    CORRECTED = "CORRECTED"
    CANCELLED = "CANCELLED"


class PresencePersonSummary(BaseModel):
    id: int
    first_name: str
    last_name: str
    person_type: str
    active: bool


class PresenceRecognitionSummary(BaseModel):
    id: int
    captured_at: datetime
    decision: str
    similarity_score: float | None
    threshold_used: float | None
    device_code: str | None


class PresenceVisitSummary(BaseModel):
    id: int
    purpose: str
    status: str
    planned_start: datetime | None
    planned_end: datetime | None


class PresenceEventRead(BaseModel):
    id: int
    person_id: int
    recognition_event_id: int | None
    visit_id: int | None
    event_type: PresenceEventType
    event_time: datetime
    source: PresenceSource
    status: PresenceStatus
    note: str | None
    created_by: int | None
    created_at: datetime
    person: PresencePersonSummary
    recognition: PresenceRecognitionSummary | None
    visit: PresenceVisitSummary | None


class PresenceFromRecognitionCreate(BaseModel):
    visit_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=500)


class PresenceRegistrationResult(BaseModel):
    message: str
    created: bool
    presence: PresenceEventRead


class PresenceEventList(BaseModel):
    items: list[PresenceEventRead]
    total: int
    offset: int
    limit: int


class CurrentPresenceList(BaseModel):
    items: list[PresenceEventRead]
    total: int


class PersonPresenceState(BaseModel):
    person: PresencePersonSummary
    is_inside: bool
    last_event: PresenceEventRead | None
