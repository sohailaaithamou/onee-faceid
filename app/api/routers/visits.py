from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.visit import (
    VisitCreate,
    VisitRead,
    VisitStatus,
    VisitStatusUpdate,
    VisitUpdate,
)
from app.services.visit_service import (
    create_visit,
    get_visit_or_404,
    list_visits,
    update_visit,
    update_visit_status,
)

router = APIRouter(prefix="/visits", tags=["Visits"])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=VisitRead,
    status_code=status.HTTP_201_CREATED,
)
def create_visit_route(
    payload: VisitCreate,
    db: SessionDependency,
) -> VisitRead:
    return create_visit(db, payload)


@router.get("", response_model=list[VisitRead])
def list_visits_route(
    db: SessionDependency,
    visit_status: VisitStatus | None = Query(default=None, alias="status"),
    visitor_person_id: int | None = Query(default=None, ge=1),
    organization_id: int | None = Query(default=None, ge=1),
    host_employee_id: int | None = Query(default=None, ge=1),
    host_unit_id: int | None = Query(default=None, ge=1),
    planned_from: datetime | None = None,
    planned_to: datetime | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=300),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[VisitRead]:
    return list_visits(
        db,
        status=visit_status,
        visitor_person_id=visitor_person_id,
        organization_id=organization_id,
        host_employee_id=host_employee_id,
        host_unit_id=host_unit_id,
        planned_from=planned_from,
        planned_to=planned_to,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/{visit_id}", response_model=VisitRead)
def get_visit_route(
    visit_id: int,
    db: SessionDependency,
) -> VisitRead:
    return get_visit_or_404(db, visit_id)


@router.put("/{visit_id}", response_model=VisitRead)
def update_visit_route(
    visit_id: int,
    payload: VisitUpdate,
    db: SessionDependency,
) -> VisitRead:
    return update_visit(db, visit_id, payload)


@router.put("/{visit_id}/status", response_model=VisitRead)
def update_visit_status_route(
    visit_id: int,
    payload: VisitStatusUpdate,
    db: SessionDependency,
) -> VisitRead:
    return update_visit_status(db, visit_id, payload)
