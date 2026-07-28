from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DashboardCounts(BaseModel):
    active_employees: int = 0
    active_visitors: int = 0
    enrolled_people: int = 0
    currently_inside: int = 0
    entries_today: int = 0
    exits_today: int = 0
    visits_today: int = 0
    visits_in_progress: int = 0
    recognitions_today: int = 0
    matched_today: int = 0
    unknown_today: int = 0
    recognition_success_rate: float = Field(default=0.0, ge=0.0, le=100.0)


class DashboardCurrentPresenceItem(BaseModel):
    presence_id: int
    person_id: int
    first_name: str
    last_name: str
    person_type: str
    event_time: datetime
    unit_name: str | None = None
    organization_name: str | None = None
    visit_id: int | None = None


class DashboardPresenceEventItem(BaseModel):
    id: int
    person_id: int
    first_name: str
    last_name: str
    person_type: str
    event_type: str
    event_time: datetime
    source: str
    status: str


class DashboardVisitItem(BaseModel):
    id: int
    visitor_person_id: int
    visitor_name: str
    organization_name: str
    purpose: str
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    status: str
    host_employee_name: str | None = None
    host_unit_name: str | None = None


class DashboardRecognitionBreakdownItem(BaseModel):
    decision: str
    count: int


class DashboardTrendItem(BaseModel):
    day: date
    entries: int = 0
    exits: int = 0
    matched: int = 0
    unknown: int = 0
    total_recognitions: int = 0


class DashboardOverview(BaseModel):
    generated_at: datetime
    selected_day: date
    timezone: str
    counts: DashboardCounts
    current_presence: list[DashboardCurrentPresenceItem]
    recent_presence_events: list[DashboardPresenceEventItem]
    visits: list[DashboardVisitItem]
    recognition_breakdown: list[DashboardRecognitionBreakdownItem]
    trend: list[DashboardTrendItem]
