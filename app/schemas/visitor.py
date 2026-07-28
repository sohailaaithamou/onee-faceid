from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class VisitorType(str, Enum):
    INTERN = "INTERN"
    CLIENT_REPRESENTATIVE = "CLIENT_REPRESENTATIVE"
    COMPANY_REPRESENTATIVE = "COMPANY_REPRESENTATIVE"


class InternAssignmentCreate(BaseModel):
    organizational_unit_id: int = Field(ge=1)
    position_title: str | None = Field(default="Stagiaire", max_length=140)
    start_date: date
    end_date: date | None = None

    @field_validator("position_title")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_assignment_dates(self) -> "InternAssignmentCreate":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError(
                "La date de fin d'affectation ne peut pas être antérieure à sa date de début."
            )
        return self


class VisitorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    cin: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=160)

    visitor_type: VisitorType
    organization_id: int = Field(ge=1)
    valid_from: date | None = None
    valid_until: date | None = None
    active: bool = True

    initial_assignment: InternAssignmentCreate | None = None

    @field_validator("first_name", "last_name")
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

    @field_validator("phone", "email")
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
    def validate_profile(self) -> "VisitorCreate":
        if self.visitor_type == VisitorType.INTERN:
            if self.valid_from is None or self.valid_until is None:
                raise ValueError(
                    "Les dates de début et de fin sont obligatoires pour un stagiaire."
                )

            if self.valid_until < self.valid_from:
                raise ValueError(
                    "La date de fin du stage ne peut pas être antérieure à sa date de début."
                )

            if self.initial_assignment is None:
                raise ValueError(
                    "Une affectation initiale est obligatoire pour un stagiaire."
                )

            assignment_end = self.initial_assignment.end_date or self.valid_until
            if self.initial_assignment.start_date < self.valid_from:
                raise ValueError(
                    "L'affectation ne peut pas commencer avant le début du stage."
                )
            if assignment_end > self.valid_until:
                raise ValueError(
                    "L'affectation ne peut pas terminer après la fin du stage."
                )
        else:
            if self.initial_assignment is not None:
                raise ValueError(
                    "Seul un stagiaire peut recevoir une affectation interne."
                )

            if (self.valid_from is None) != (self.valid_until is None):
                raise ValueError(
                    "Fournissez les deux dates de validité ou laissez-les toutes les deux vides."
                )

            if (
                self.valid_from is not None
                and self.valid_until is not None
                and self.valid_until < self.valid_from
            ):
                raise ValueError(
                    "La date de fin de validité ne peut pas être antérieure à sa date de début."
                )

        return self


class VisitorUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    cin: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=160)

    organization_id: int | None = Field(default=None, ge=1)
    valid_from: date | None = None
    valid_until: date | None = None
    active: bool | None = None

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

    @field_validator("phone", "email")
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
    def require_at_least_one_field(self) -> "VisitorUpdate":
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni pour la modification.")
        return self


class ExternalOrganizationSummary(BaseModel):
    id: int
    legal_name: str
    short_name: str | None
    organization_type: str
    relationship_to_onee: str
    city: str | None


class VisitorOrganizationalUnitSummary(BaseModel):
    id: int
    code: str
    name: str
    unit_type: str


class VisitorAssignmentRead(BaseModel):
    id: int
    organizational_unit_id: int
    position_title: str | None
    start_date: date
    end_date: date | None
    is_primary: bool
    organizational_unit: VisitorOrganizationalUnitSummary


class VisitorRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    cin: str | None
    phone: str | None
    email: str | None
    active: bool
    created_at: datetime
    updated_at: datetime

    visitor_type: VisitorType
    organization_id: int
    valid_from: date | None
    valid_until: date | None
    profile_active: bool
    organization: ExternalOrganizationSummary
    current_assignment: VisitorAssignmentRead | None


class VisitorDetailRead(VisitorRead):
    assignments: list[VisitorAssignmentRead]
