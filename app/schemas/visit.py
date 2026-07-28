from __future__ import annotations

from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

MOROCCO_TZ = ZoneInfo("Africa/Casablanca")


class VisitStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REFUSED = "REFUSED"


def _ensure_timezone(value: datetime | None) -> datetime | None:
    """Interprète une date sans fuseau comme une heure locale du Maroc."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=MOROCCO_TZ)
    return value


class VisitCreate(BaseModel):
    visitor_person_id: int = Field(ge=1)
    organization_id: int | None = Field(default=None, ge=1)
    host_employee_id: int | None = Field(default=None, ge=1)
    host_unit_id: int | None = Field(default=None, ge=1)
    purpose: str = Field(min_length=1, max_length=300)
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    created_by: int | None = Field(default=None, ge=1)

    @field_validator("purpose")
    @classmethod
    def clean_purpose(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le motif de la visite ne peut pas être vide.")
        return value

    @field_validator("planned_start", "planned_end")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return _ensure_timezone(value)

    @model_validator(mode="after")
    def validate_visit(self) -> "VisitCreate":
        if self.host_employee_id is None and self.host_unit_id is None:
            raise ValueError(
                "Indiquez au moins un agent hôte ou une unité organisationnelle hôte."
            )

        if (self.planned_start is None) != (self.planned_end is None):
            raise ValueError(
                "Fournissez les deux heures prévues ou laissez-les toutes les deux vides."
            )

        if (
            self.planned_start is not None
            and self.planned_end is not None
            and self.planned_end < self.planned_start
        ):
            raise ValueError(
                "La fin prévue ne peut pas être antérieure au début prévu."
            )

        return self


class VisitUpdate(BaseModel):
    organization_id: int | None = Field(default=None, ge=1)
    host_employee_id: int | None = Field(default=None, ge=1)
    host_unit_id: int | None = Field(default=None, ge=1)
    purpose: str | None = Field(default=None, min_length=1, max_length=300)
    planned_start: datetime | None = None
    planned_end: datetime | None = None

    @field_validator("purpose")
    @classmethod
    def clean_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Le motif de la visite ne peut pas être vide.")
        return value

    @field_validator("planned_start", "planned_end")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return _ensure_timezone(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "VisitUpdate":
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni pour la modification.")
        return self


class VisitStatusUpdate(BaseModel):
    status: VisitStatus


class VisitPersonSummary(BaseModel):
    id: int
    first_name: str
    last_name: str
    cin: str | None
    visitor_type: str


class VisitOrganizationSummary(BaseModel):
    id: int
    legal_name: str
    short_name: str | None
    organization_type: str
    relationship_to_onee: str


class VisitHostEmployeeSummary(BaseModel):
    person_id: int
    first_name: str
    last_name: str
    matricule: str
    job_title: str | None


class VisitHostUnitSummary(BaseModel):
    id: int
    code: str
    name: str
    unit_type: str


class VisitCreatorSummary(BaseModel):
    id: int
    username: str
    role: str


class VisitRead(BaseModel):
    id: int
    visitor_person_id: int
    organization_id: int
    host_employee_id: int | None
    host_unit_id: int | None
    purpose: str
    planned_start: datetime | None
    planned_end: datetime | None
    status: VisitStatus
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    visitor: VisitPersonSummary
    organization: VisitOrganizationSummary
    host_employee: VisitHostEmployeeSummary | None
    host_unit: VisitHostUnitSummary | None
    creator: VisitCreatorSummary | None
