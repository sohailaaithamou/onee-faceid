from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AttendanceSettings(BaseSettings):
    """Configuration du pointage automatique après reconnaissance faciale."""

    cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    require_visit_for_visitors: bool = True
    auto_update_visit_status: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ATTENDANCE_",
        extra="ignore",
    )


@lru_cache
def get_attendance_settings() -> AttendanceSettings:
    return AttendanceSettings()


attendance_settings = get_attendance_settings()
