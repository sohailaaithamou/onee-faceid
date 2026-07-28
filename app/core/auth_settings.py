from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Configuration de l'authentification JWT du dashboard."""

    secret_key: str = Field(min_length=32)
    algorithm: str = "HS256"
    access_token_minutes: int = Field(default=60, ge=5, le=1440)
    issuer: str = "onee-faceid"
    audience: str = "onee-faceid-dashboard"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AUTH_",
        extra="ignore",
    )


auth_settings = AuthSettings()
