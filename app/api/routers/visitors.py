from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.visitor import (
    InternAssignmentCreate,
    VisitorCreate,
    VisitorDetailRead,
    VisitorRead,
    VisitorType,
    VisitorUpdate,
)
from app.services.visitor_service import (
    create_intern_assignment,
    create_visitor,
    get_visitor_or_404,
    list_visitors,
    update_visitor,
)

router = APIRouter(prefix="/visitors", tags=["Visitors"])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=VisitorDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_visitor_route(
    payload: VisitorCreate,
    db: SessionDependency,
) -> VisitorDetailRead:
    return create_visitor(db, payload)


@router.get("", response_model=list[VisitorRead])
def list_visitors_route(
    db: SessionDependency,
    active: bool | None = None,
    visitor_type: VisitorType | None = None,
    organization_id: int | None = Query(default=None, ge=1),
    organizational_unit_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, min_length=1, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[VisitorRead]:
    return list_visitors(
        db,
        active=active,
        visitor_type=visitor_type,
        organization_id=organization_id,
        organizational_unit_id=organizational_unit_id,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/{person_id}", response_model=VisitorDetailRead)
def get_visitor_route(
    person_id: int,
    db: SessionDependency,
) -> VisitorDetailRead:
    return get_visitor_or_404(db, person_id)


@router.put("/{person_id}", response_model=VisitorDetailRead)
def update_visitor_route(
    person_id: int,
    payload: VisitorUpdate,
    db: SessionDependency,
) -> VisitorDetailRead:
    return update_visitor(db, person_id, payload)


@router.post(
    "/{person_id}/assignments",
    response_model=VisitorDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_intern_assignment_route(
    person_id: int,
    payload: InternAssignmentCreate,
    db: SessionDependency,
) -> VisitorDetailRead:
    return create_intern_assignment(db, person_id, payload)
