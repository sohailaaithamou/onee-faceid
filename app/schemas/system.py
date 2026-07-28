from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SystemCheckState(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class SystemCheck(BaseModel):
    key: str
    label: str
    state: SystemCheckState
    detail: str
    value: Any | None = None


class SystemReadinessSummary(BaseModel):
    passed: int = Field(default=0, ge=0)
    warnings: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class SystemReadiness(BaseModel):
    status: Literal["READY", "WARNING", "NOT_READY"]
    generated_at: datetime
    database: str | None = None
    database_user: str | None = None
    current_schema: str | None = None
    summary: SystemReadinessSummary
    checks: list[SystemCheck]
