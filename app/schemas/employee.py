from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EmploymentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ENDED = "ENDED"


class InitialAssignmentCreate(BaseModel):
    organizational_unit_id: int = Field(ge=1)
    position_title: str | None = Field(default=None, max_length=140)
    start_date: date

    @field_validator("position_title")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class EmployeeCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    cin: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=160)

    matricule: str = Field(min_length=1, max_length=50)
    hire_date: date
    end_date: date | None = None
    job_title: str | None = Field(default=None, max_length=140)
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE

    initial_assignment: InitialAssignmentCreate

    @field_validator("first_name", "last_name", "matricule")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ce champ ne peut pas être vide.")
        return value

    @field_validator("cin")
    @classmethod
    def normalize_cin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None

    @field_validator("matricule")
    @classmethod
    def normalize_matricule(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("phone", "email", "job_title")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lower()

    @model_validator(mode="after")
    def validate_dates_and_status(self) -> "EmployeeCreate":
        if self.employment_status == EmploymentStatus.ENDED:
            if self.end_date is None:
                raise ValueError(
                    "La date de fin est obligatoire lorsque le statut est ENDED."
                )
        elif self.end_date is not None:
            raise ValueError(
                "La date de fin doit être vide pour un agent ACTIVE ou SUSPENDED."
            )

        if self.end_date is not None and self.end_date < self.hire_date:
            raise ValueError(
                "La date de fin ne peut pas être antérieure à la date d'embauche."
            )

        if self.initial_assignment.start_date < self.hire_date:
            raise ValueError(
                "L'affectation initiale ne peut pas commencer avant la date d'embauche."
            )

        if (
            self.end_date is not None
            and self.initial_assignment.start_date > self.end_date
        ):
            raise ValueError(
                "L'affectation initiale ne peut pas commencer après la fin d'emploi."
            )

        return self


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    cin: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=160)

    matricule: str | None = Field(default=None, min_length=1, max_length=50)
    hire_date: date | None = None
    end_date: date | None = None
    job_title: str | None = Field(default=None, max_length=140)
    employment_status: EmploymentStatus | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Le nom et le prénom ne peuvent pas être vides.")
        return value

    @field_validator("cin")
    @classmethod
    def normalize_cin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None

    @field_validator("matricule")
    @classmethod
    def normalize_matricule(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not value:
            raise ValueError("Le matricule ne peut pas être vide.")
        return value

    @field_validator("phone", "email", "job_title")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lower()

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "EmployeeUpdate":
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni pour la modification.")
        return self


class EmployeeAssignmentCreate(BaseModel):
    organizational_unit_id: int = Field(ge=1)
    position_title: str | None = Field(default=None, max_length=140)
    start_date: date

    @field_validator("position_title")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class OrganizationalUnitSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    unit_type: str


class AssignmentRead(BaseModel):
    id: int
    organizational_unit_id: int
    position_title: str | None
    start_date: date
    end_date: date | None
    is_primary: bool
    organizational_unit: OrganizationalUnitSummary


class EmployeeRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    cin: str | None
    phone: str | None
    email: str | None
    active: bool
    created_at: datetime
    updated_at: datetime

    matricule: str
    hire_date: date
    end_date: date | None
    job_title: str | None
    employment_status: EmploymentStatus

    current_assignment: AssignmentRead | None


class EmployeeDetailRead(EmployeeRead):
    assignments: list[AssignmentRead]
