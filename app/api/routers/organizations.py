from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.organization import (
    ExternalOrganizationCreate,
    ExternalOrganizationRead,
    ExternalOrganizationUpdate,
    OrganizationRelationship,
    OrganizationType,
)
from app.services.organization_service import (
    create_organization,
    get_organization_or_404,
    list_organizations,
    update_organization,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=ExternalOrganizationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organization_route(
    payload: ExternalOrganizationCreate,
    db: SessionDependency,
) -> ExternalOrganizationRead:
    return create_organization(db, payload)


@router.get("", response_model=list[ExternalOrganizationRead])
def list_organizations_route(
    db: SessionDependency,
    active: bool | None = None,
    organization_type: OrganizationType | None = None,
    relationship_to_onee: OrganizationRelationship | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ExternalOrganizationRead]:
    return list_organizations(
        db,
        active=active,
        organization_type=organization_type,
        relationship_to_onee=relationship_to_onee,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/{organization_id}", response_model=ExternalOrganizationRead)
def get_organization_route(
    organization_id: int,
    db: SessionDependency,
) -> ExternalOrganizationRead:
    return get_organization_or_404(db, organization_id)


@router.put("/{organization_id}", response_model=ExternalOrganizationRead)
def update_organization_route(
    organization_id: int,
    payload: ExternalOrganizationUpdate,
    db: SessionDependency,
) -> ExternalOrganizationRead:
    return update_organization(db, organization_id, payload)
