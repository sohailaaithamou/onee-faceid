from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
)
from app.models import OrganizationalUnit
from app.schemas.organizational_unit import (
    OrganizationalUnitCreate,
    OrganizationalUnitType,
    OrganizationalUnitUpdate,
)


def _get_constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint_name = _get_constraint_name(exc)
        if constraint_name == "uq_organizational_unit_code_ci":
            raise ConflictError(
                "Une unité organisationnelle portant ce code existe déjà."
            ) from exc

        raise ConflictError(
            "L'unité ne peut pas être enregistrée à cause d'une contrainte de données."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enregistrement de l'unité."
    ) from exc


def get_unit_or_404(db: Session, unit_id: int) -> OrganizationalUnit:
    try:
        unit = db.get(OrganizationalUnit, unit_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'unité dans PostgreSQL."
        ) from exc

    if unit is None:
        raise NotFoundError("Unité organisationnelle introuvable.")

    return unit


def _get_parent_or_error(
    db: Session,
    parent_id: int | None,
) -> OrganizationalUnit | None:
    if parent_id is None:
        return None

    parent = get_unit_or_404(db, parent_id)
    if not parent.active:
        raise BusinessRuleError(
            "L'unité parente est désactivée. Activez-la avant de l'utiliser."
        )
    return parent


def _validate_hierarchy(
    *,
    unit_type: OrganizationalUnitType,
    parent: OrganizationalUnit | None,
) -> None:
    if unit_type == OrganizationalUnitType.REGIONAL_DIRECTION:
        if parent is not None:
            raise BusinessRuleError(
                "Une direction régionale ne doit pas avoir d'unité parente."
            )
        return

    if parent is None:
        raise BusinessRuleError(
            f"Une unité de type {unit_type.value} doit avoir une unité parente."
        )

    if unit_type == OrganizationalUnitType.DIVISION:
        if parent.unit_type != OrganizationalUnitType.REGIONAL_DIRECTION.value:
            raise BusinessRuleError(
                "Une division doit appartenir directement à une direction régionale."
            )
        return

    if unit_type == OrganizationalUnitType.SERVICE:
        if parent.unit_type != OrganizationalUnitType.DIVISION.value:
            raise BusinessRuleError(
                "Un service doit appartenir directement à une division."
            )
        return


def create_organizational_unit(
    db: Session,
    payload: OrganizationalUnitCreate,
) -> OrganizationalUnit:
    parent = _get_parent_or_error(db, payload.parent_id)
    _validate_hierarchy(unit_type=payload.unit_type, parent=parent)

    unit = OrganizationalUnit(**payload.model_dump(mode="json"))
    db.add(unit)

    try:
        db.commit()
        db.refresh(unit)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return unit


def list_organizational_units(
    db: Session,
    *,
    active: bool | None = None,
    unit_type: OrganizationalUnitType | None = None,
    parent_id: int | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[OrganizationalUnit]:
    statement = select(OrganizationalUnit)

    if active is not None:
        statement = statement.where(OrganizationalUnit.active == active)

    if unit_type is not None:
        statement = statement.where(OrganizationalUnit.unit_type == unit_type.value)

    if parent_id is not None:
        statement = statement.where(OrganizationalUnit.parent_id == parent_id)

    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                OrganizationalUnit.code.ilike(pattern),
                OrganizationalUnit.name.ilike(pattern),
            )
        )

    statement = statement.order_by(
        OrganizationalUnit.unit_type,
        func.lower(OrganizationalUnit.code),
        OrganizationalUnit.id,
    ).offset(offset).limit(limit)

    try:
        return list(db.scalars(statement).all())
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de charger les unités organisationnelles depuis PostgreSQL."
        ) from exc


def update_organizational_unit(
    db: Session,
    unit_id: int,
    payload: OrganizationalUnitUpdate,
) -> OrganizationalUnit:
    unit = get_unit_or_404(db, unit_id)
    updates = payload.model_dump(exclude_unset=True, mode="json")

    requested_type_value = updates.get("unit_type", unit.unit_type)
    requested_type = OrganizationalUnitType(requested_type_value)
    requested_parent_id = updates.get("parent_id", unit.parent_id)

    if requested_parent_id == unit.id:
        raise BusinessRuleError("Une unité ne peut pas être son propre parent.")

    parent = _get_parent_or_error(db, requested_parent_id)
    _validate_hierarchy(unit_type=requested_type, parent=parent)

    if requested_type.value != unit.unit_type:
        child_count = db.scalar(
            select(func.count())
            .select_from(OrganizationalUnit)
            .where(OrganizationalUnit.parent_id == unit.id)
        )
        if child_count:
            raise BusinessRuleError(
                "Le type d'une unité ayant des unités enfants ne peut pas être modifié."
            )

    if updates.get("active") is False and unit.active:
        active_child_count = db.scalar(
            select(func.count())
            .select_from(OrganizationalUnit)
            .where(
                OrganizationalUnit.parent_id == unit.id,
                OrganizationalUnit.active.is_(True),
            )
        )
        if active_child_count:
            raise BusinessRuleError(
                "Désactivez d'abord les unités enfants actives."
            )

    for field_name, value in updates.items():
        setattr(unit, field_name, value)

    try:
        db.commit()
        db.refresh(unit)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return unit
