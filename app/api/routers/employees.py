from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.employee import (
    EmployeeAssignmentCreate,
    EmployeeCreate,
    EmployeeDetailRead,
    EmployeeRead,
    EmployeeUpdate,
    EmploymentStatus,
)
from app.services.employee_service import (
    create_employee,
    create_employee_assignment,
    get_employee_or_404,
    list_employees,
    update_employee,
)

router = APIRouter(prefix="/employees", tags=["Employees"])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=EmployeeDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_employee_route(
    payload: EmployeeCreate,
    db: SessionDependency,
) -> EmployeeDetailRead:
    return create_employee(db, payload)


@router.get("", response_model=list[EmployeeRead])
def list_employees_route(
    db: SessionDependency,
    active: bool | None = None,
    employment_status: EmploymentStatus | None = None,
    organizational_unit_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, min_length=1, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[EmployeeRead]:
    return list_employees(
        db,
        active=active,
        employment_status=employment_status,
        organizational_unit_id=organizational_unit_id,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/{person_id}", response_model=EmployeeDetailRead)
def get_employee_route(
    person_id: int,
    db: SessionDependency,
) -> EmployeeDetailRead:
    return get_employee_or_404(db, person_id)


@router.put("/{person_id}", response_model=EmployeeDetailRead)
def update_employee_route(
    person_id: int,
    payload: EmployeeUpdate,
    db: SessionDependency,
) -> EmployeeDetailRead:
    return update_employee(db, person_id, payload)


@router.post(
    "/{person_id}/assignments",
    response_model=EmployeeDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_employee_assignment_route(
    person_id: int,
    payload: EmployeeAssignmentCreate,
    db: SessionDependency,
) -> EmployeeDetailRead:
    return create_employee_assignment(db, person_id, payload)
