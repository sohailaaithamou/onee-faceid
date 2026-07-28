from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrganizationType(str, Enum):
    COMPANY = "COMPANY"
    TELECOM_OPERATOR = "TELECOM_OPERATOR"
    PUBLIC_ORGANIZATION = "PUBLIC_ORGANIZATION"
    LOCAL_AUTHORITY = "LOCAL_AUTHORITY"
    ASSOCIATION = "ASSOCIATION"
    UNIVERSITY = "UNIVERSITY"
    SCHOOL = "SCHOOL"
    ARMED_FORCES = "ARMED_FORCES"
    OTHER = "OTHER"


class OrganizationRelationship(str, Enum):
    CLIENT = "CLIENT"
    PARTNER = "PARTNER"
    SUPPLIER = "SUPPLIER"
    SERVICE_PROVIDER = "SERVICE_PROVIDER"
    TRAINING_INSTITUTION = "TRAINING_INSTITUTION"
    OTHER = "OTHER"


class ExternalOrganizationBase(BaseModel):
    legal_name: str = Field(min_length=1, max_length=160)
    short_name: str | None = Field(default=None, max_length=60)
    organization_type: OrganizationType
    relationship_to_onee: OrganizationRelationship
    city: str | None = Field(default=None, max_length=100)
    active: bool = True

    @field_validator("legal_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom officiel ne peut pas être vide.")
        return value

    @field_validator("short_name", "city")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ExternalOrganizationCreate(ExternalOrganizationBase):
    pass


class ExternalOrganizationUpdate(BaseModel):
    legal_name: str | None = Field(default=None, min_length=1, max_length=160)
    short_name: str | None = Field(default=None, max_length=60)
    organization_type: OrganizationType | None = None
    relationship_to_onee: OrganizationRelationship | None = None
    city: str | None = Field(default=None, max_length=100)
    active: bool | None = None

    @field_validator("legal_name")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Le nom officiel ne peut pas être vide.")
        return value

    @field_validator("short_name", "city")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "ExternalOrganizationUpdate":
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni pour la modification.")
        return self


class ExternalOrganizationRead(ExternalOrganizationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
