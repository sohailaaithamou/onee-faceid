from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrganizationalUnitType(str, Enum):
    REGIONAL_DIRECTION = "REGIONAL_DIRECTION"
    DIVISION = "DIVISION"
    SERVICE = "SERVICE"


class OrganizationalUnitBase(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=160)
    unit_type: OrganizationalUnitType
    parent_id: int | None = Field(default=None, ge=1)
    active: bool = True

    @field_validator("code", "name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le code et le nom ne peuvent pas être vides.")
        return value


class OrganizationalUnitCreate(OrganizationalUnitBase):
    pass


class OrganizationalUnitUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    unit_type: OrganizationalUnitType | None = None
    parent_id: int | None = Field(default=None, ge=1)
    active: bool | None = None

    @field_validator("code", "name")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Le code et le nom ne peuvent pas être vides.")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "OrganizationalUnitUpdate":
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni pour la modification.")
        return self


class OrganizationalUnitRead(OrganizationalUnitBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
