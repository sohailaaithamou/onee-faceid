from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.organizational_unit import (
    OrganizationalUnitCreate,
    OrganizationalUnitRead,
    OrganizationalUnitType,
    OrganizationalUnitUpdate,
)
from app.services.organizational_unit_service import (
    create_organizational_unit,
    get_unit_or_404,
    list_organizational_units,
    update_organizational_unit,
)

router = APIRouter(
    prefix="/organizational-units",
    tags=["Organizational Units"],
)
SessionDependency = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=OrganizationalUnitRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organizational_unit_route(
    payload: OrganizationalUnitCreate,
    db: SessionDependency,
) -> OrganizationalUnitRead:
    return create_organizational_unit(db, payload)


@router.get("", response_model=list[OrganizationalUnitRead])
def list_organizational_units_route(
    db: SessionDependency,
    active: bool | None = None,
    unit_type: OrganizationalUnitType | None = None,
    parent_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, min_length=1, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[OrganizationalUnitRead]:
    return list_organizational_units(
        db,
        active=active,
        unit_type=unit_type,
        parent_id=parent_id,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/{unit_id}", response_model=OrganizationalUnitRead)
def get_organizational_unit_route(
    unit_id: int,
    db: SessionDependency,
) -> OrganizationalUnitRead:
    return get_unit_or_404(db, unit_id)


@router.put("/{unit_id}", response_model=OrganizationalUnitRead)
def update_organizational_unit_route(
    unit_id: int,
    payload: OrganizationalUnitUpdate,
    db: SessionDependency,
) -> OrganizationalUnitRead:
    return update_organizational_unit(db, unit_id, payload)
