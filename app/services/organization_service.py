from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, DatabaseOperationError, NotFoundError
from app.models import ExternalOrganization
from app.schemas.organization import (
    ExternalOrganizationCreate,
    ExternalOrganizationUpdate,
    OrganizationRelationship,
    OrganizationType,
)


def _get_constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint_name = _get_constraint_name(exc)
        if constraint_name == "uq_external_organization_legal_name_ci":
            raise ConflictError(
                "Une organisation portant ce nom officiel existe déjà."
            ) from exc

        raise ConflictError(
            "L'organisation ne peut pas être enregistrée à cause d'une contrainte de données."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enregistrement de l'organisation."
    ) from exc


def get_organization_or_404(db: Session, organization_id: int) -> ExternalOrganization:
    try:
        organization = db.get(ExternalOrganization, organization_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'organisation dans PostgreSQL."
        ) from exc

    if organization is None:
        raise NotFoundError("Organisation introuvable.")

    return organization


def create_organization(
    db: Session,
    payload: ExternalOrganizationCreate,
) -> ExternalOrganization:
    organization = ExternalOrganization(**payload.model_dump(mode="json"))
    db.add(organization)

    try:
        db.commit()
        db.refresh(organization)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return organization


def list_organizations(
    db: Session,
    *,
    active: bool | None = None,
    organization_type: OrganizationType | None = None,
    relationship_to_onee: OrganizationRelationship | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[ExternalOrganization]:
    statement = select(ExternalOrganization)

    if active is not None:
        statement = statement.where(ExternalOrganization.active == active)

    if organization_type is not None:
        statement = statement.where(
            ExternalOrganization.organization_type == organization_type.value
        )

    if relationship_to_onee is not None:
        statement = statement.where(
            ExternalOrganization.relationship_to_onee
            == relationship_to_onee.value
        )

    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                ExternalOrganization.legal_name.ilike(pattern),
                ExternalOrganization.short_name.ilike(pattern),
                ExternalOrganization.city.ilike(pattern),
            )
        )

    statement = statement.order_by(
        func.lower(ExternalOrganization.legal_name),
        ExternalOrganization.id,
    ).offset(offset).limit(limit)

    try:
        return list(db.scalars(statement).all())
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de charger les organisations depuis PostgreSQL."
        ) from exc


def update_organization(
    db: Session,
    organization_id: int,
    payload: ExternalOrganizationUpdate,
) -> ExternalOrganization:
    organization = get_organization_or_404(db, organization_id)

    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field_name, value in updates.items():
        setattr(organization, field_name, value)

    try:
        db.commit()
        db.refresh(organization)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return organization
