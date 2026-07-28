from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FaceEnrollmentPersonSummary(BaseModel):
    id: int
    first_name: str
    last_name: str
    person_type: str
    active: bool


class FaceEmbeddingRead(BaseModel):
    id: int
    person_id: int
    model_name: str
    model_version: str
    capture_label: str | None
    quality_score: float | None
    is_active: bool
    created_at: datetime


class FaceCaptureDiagnostic(BaseModel):
    capture_label: str
    filename: str
    detection_score: float
    sharpness_score: float
    face_width: int
    face_height: int
    quality_score: float


class FaceSimilaritySummary(BaseModel):
    front_left: float
    front_right: float
    left_right: float
    minimum: float
    required_minimum: float


class FaceEnrollmentResult(BaseModel):
    message: str
    person: FaceEnrollmentPersonSummary
    embeddings: list[FaceEmbeddingRead]
    diagnostics: list[FaceCaptureDiagnostic]
    similarities: FaceSimilaritySummary


class PersonFaceEmbeddingsRead(BaseModel):
    person: FaceEnrollmentPersonSummary
    embeddings: list[FaceEmbeddingRead]
    total: int


class FaceEmbeddingStatusUpdate(BaseModel):
    is_active: bool = Field(description="Active ou désactive l'embedding sans le supprimer.")
