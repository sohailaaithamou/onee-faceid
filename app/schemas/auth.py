from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    RECEPTION = "RECEPTION"
    VIEWER = "VIEWER"


class AccountPersonSummary(BaseModel):
    id: int
    first_name: str
    last_name: str
    person_type: str
    active: bool

    model_config = ConfigDict(from_attributes=True)


class UserAccountResponse(BaseModel):
    id: int
    person_id: int | None
    username: str
    role: UserRole
    active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    person: AccountPersonSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class UserAccountCreate(BaseModel):
    person_id: int | None = Field(default=None, ge=1)
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=128)
    role: UserRole
    active: bool = True

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom d'utilisateur est obligatoire.")
        if any(character.isspace() for character in value):
            raise ValueError("Le nom d'utilisateur ne doit pas contenir d'espace.")
        return value


class UserAccountUpdate(BaseModel):
    person_id: int | None = Field(default=None, ge=1)
    username: str | None = Field(default=None, min_length=3, max_length=80)
    role: UserRole | None = None
    active: bool | None = None

    @field_validator("username")
    @classmethod
    def clean_optional_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Le nom d'utilisateur est obligatoire.")
        if any(character.isspace() for character in value):
            raise ValueError("Le nom d'utilisateur ne doit pas contenir d'espace.")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UserAccountUpdate":
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni.")
        return self


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=10, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @model_validator(mode="after")
    def passwords_must_differ(self) -> "PasswordChangeRequest":
        if self.current_password == self.new_password:
            raise ValueError("Le nouveau mot de passe doit être différent de l'ancien.")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    account: UserAccountResponse


class MessageResponse(BaseModel):
    message: str
