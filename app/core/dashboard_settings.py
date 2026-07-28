from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    """Configuration du tableau de bord opérationnel."""

    timezone: str = "Africa/Casablanca"
    recent_events_limit: int = Field(default=12, ge=5, le=100)
    current_presence_limit: int = Field(default=100, ge=10, le=500)
    visits_limit: int = Field(default=100, ge=10, le=500)
    trend_days: int = Field(default=7, ge=3, le=31)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DASHBOARD_",
        extra="ignore",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "Fuseau horaire inconnu. Exemple valide : Africa/Casablanca."
            ) from exc
        return value


@lru_cache
def get_dashboard_settings() -> DashboardSettings:
    return DashboardSettings()


dashboard_settings = get_dashboard_settings()
