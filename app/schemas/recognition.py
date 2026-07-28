from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RecognitionDecision(str, Enum):
    MATCHED = "MATCHED"
    UNKNOWN = "UNKNOWN"
    SPOOF_DETECTED = "SPOOF_DETECTED"
    LOW_QUALITY = "LOW_QUALITY"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    ERROR = "ERROR"


class RecognitionPersonSummary(BaseModel):
    id: int
    first_name: str
    last_name: str
    person_type: str
    active: bool


class RecognitionCandidate(BaseModel):
    person_id: int
    first_name: str
    last_name: str
    person_type: str
    similarity_score: float
    embedding_id: int
    capture_label: str | None


class RecognitionDiagnostic(BaseModel):
    detection_score: float
    sharpness_score: float
    face_width: int
    face_height: int
    quality_score: float


class RecognitionEventRead(BaseModel):
    id: int
    matched_person_id: int | None
    captured_at: datetime
    decision: RecognitionDecision
    similarity_score: float | None
    threshold_used: float | None
    liveness_score: float | None
    model_name: str
    model_version: str
    processing_time_ms: int | None
    device_code: str | None
    snapshot_path: str | None
    error_message: str | None
    matched_person: RecognitionPersonSummary | None


class RecognitionAttemptResult(BaseModel):
    message: str
    event: RecognitionEventRead
    diagnostic: RecognitionDiagnostic | None
    candidates: list[RecognitionCandidate]
    indexed_embeddings: int
    indexed_persons: int


class RecognitionEventList(BaseModel):
    items: list[RecognitionEventRead]
    total: int
    offset: int
    limit: int


class RecognitionIndexStatus(BaseModel):
    loaded: bool
    embeddings_count: int = 0
    persons_count: int = 0
    refreshed_at: datetime | None = None
    expires_in_seconds: int | None = None
    model_version: str


class RecognitionQueryOptions(BaseModel):
    device_code: str | None = Field(default=None, max_length=80)
    refresh_index: bool = False
