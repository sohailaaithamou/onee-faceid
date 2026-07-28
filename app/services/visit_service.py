from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
)
from app.models import (
    EmployeeProfile,
    ExternalOrganization,
    OrganizationalUnit,
    Person,
    UserAccount,
    Visit,
    VisitorProfile,
)
from app.schemas.visit import VisitCreate, VisitStatus, VisitStatusUpdate, VisitUpdate


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    VisitStatus.PLANNED.value: {
        VisitStatus.IN_PROGRESS.value,
        VisitStatus.CANCELLED.value,
        VisitStatus.REFUSED.value,
    },
    VisitStatus.IN_PROGRESS.value: {
        VisitStatus.COMPLETED.value,
    },
    VisitStatus.COMPLETED.value: set(),
    VisitStatus.CANCELLED.value: set(),
    VisitStatus.REFUSED.value: set(),
}


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint = _constraint_name(exc)

        if constraint == "chk_visit_has_host":
            raise BusinessRuleError(
                "La visite doit avoir un agent hôte ou une unité hôte."
            ) from exc

        if constraint == "chk_visit_dates":
            raise BusinessRuleError(
                "La fin prévue ne peut pas être antérieure au début prévu."
            ) from exc

        if constraint == "chk_visit_status":
            raise BusinessRuleError("Le statut de la visite est invalide.") from exc

        if constraint == "fk_visit_visitor":
            raise NotFoundError("Le profil visiteur est introuvable.") from exc

        if constraint == "fk_visit_organization":
            raise NotFoundError("L'organisation externe est introuvable.") from exc

        if constraint == "fk_visit_host_employee":
            raise NotFoundError("L'agent hôte est introuvable.") from exc

        if constraint == "fk_visit_host_unit":
            raise NotFoundError("L'unité hôte est introuvable.") from exc

        if constraint == "fk_visit_created_by":
            raise NotFoundError("Le compte créateur est introuvable.") from exc

        raise ConflictError(
            "La visite ne peut pas être enregistrée à cause d'une contrainte de données."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enregistrement de la visite."
    ) from exc


def _get_active_visitor(
    db: Session,
    person_id: int,
) -> tuple[Person, VisitorProfile]:
    statement = (
        select(Person, VisitorProfile)
        .join(VisitorProfile, VisitorProfile.person_id == Person.id)
        .where(Person.id == person_id, Person.person_type == "VISITOR")
    )

    try:
        row = db.execute(statement).one_or_none()
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter le visiteur."
        ) from exc

    if row is None:
        raise NotFoundError("Visiteur introuvable.")

    person, profile = row
    if not person.active or not profile.active:
        raise BusinessRuleError(
            "Le visiteur est désactivé et ne peut pas être associé à une nouvelle visite."
        )

    return person, profile


def _get_active_organization(
    db: Session,
    organization_id: int,
) -> ExternalOrganization:
    try:
        organization = db.get(ExternalOrganization, organization_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'organisation externe."
        ) from exc

    if organization is None:
        raise NotFoundError("Organisation externe introuvable.")

    if not organization.active:
        raise BusinessRuleError(
            "L'organisation externe est désactivée et ne peut pas être utilisée."
        )

    return organization


def _get_active_host_employee(
    db: Session,
    person_id: int,
    *,
    reference_date: date,
) -> tuple[Person, EmployeeProfile]:
    statement = (
        select(Person, EmployeeProfile)
        .join(EmployeeProfile, EmployeeProfile.person_id == Person.id)
        .where(Person.id == person_id, Person.person_type == "EMPLOYEE")
    )

    try:
        row = db.execute(statement).one_or_none()
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter l'agent hôte.") from exc

    if row is None:
        raise NotFoundError("Agent hôte introuvable.")

    person, profile = row
    if not person.active or profile.employment_status != "ACTIVE":
        raise BusinessRuleError(
            "L'agent hôte n'est pas actif et ne peut pas recevoir cette visite."
        )

    if reference_date < profile.hire_date:
        raise BusinessRuleError(
            "La visite ne peut pas être planifiée avant la date d'embauche de l'agent hôte."
        )

    if profile.end_date is not None and reference_date > profile.end_date:
        raise BusinessRuleError(
            "La visite ne peut pas être planifiée après la fin d'emploi de l'agent hôte."
        )

    return person, profile


def _get_active_host_unit(
    db: Session,
    unit_id: int,
) -> OrganizationalUnit:
    try:
        unit = db.get(OrganizationalUnit, unit_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter l'unité hôte.") from exc

    if unit is None:
        raise NotFoundError("Unité organisationnelle hôte introuvable.")

    if not unit.active:
        raise BusinessRuleError(
            "L'unité organisationnelle hôte est désactivée."
        )

    return unit


def _get_active_creator(db: Session, user_id: int) -> UserAccount:
    try:
        account = db.get(UserAccount, user_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter le compte créateur.") from exc

    if account is None:
        raise NotFoundError("Compte créateur introuvable.")

    if not account.active:
        raise BusinessRuleError("Le compte créateur est désactivé.")

    return account


def _visit_reference_date(planned_start: datetime | None) -> date:
    return planned_start.date() if planned_start is not None else date.today()


def _validate_visitor_validity(
    profile: VisitorProfile,
    *,
    reference_date: date,
) -> None:
    if profile.valid_from is not None and reference_date < profile.valid_from:
        raise BusinessRuleError(
            "La visite est prévue avant le début de validité du profil visiteur."
        )

    if profile.valid_until is not None and reference_date > profile.valid_until:
        raise BusinessRuleError(
            "La visite est prévue après la fin de validité du profil visiteur."
        )


def _validate_schedule(
    planned_start: datetime | None,
    planned_end: datetime | None,
) -> None:
    if (planned_start is None) != (planned_end is None):
        raise BusinessRuleError(
            "Fournissez les deux heures prévues ou laissez-les toutes les deux vides."
        )

    if (
        planned_start is not None
        and planned_end is not None
        and planned_end < planned_start
    ):
        raise BusinessRuleError(
            "La fin prévue ne peut pas être antérieure au début prévu."
        )


def _validate_hosts(host_employee_id: int | None, host_unit_id: int | None) -> None:
    if host_employee_id is None and host_unit_id is None:
        raise BusinessRuleError(
            "Indiquez au moins un agent hôte ou une unité organisationnelle hôte."
        )


def _visit_query():
    visitor_person = aliased(Person, name="visitor_person")
    host_person = aliased(Person, name="host_person")

    statement = (
        select(
            Visit,
            VisitorProfile,
            visitor_person,
            ExternalOrganization,
            EmployeeProfile,
            host_person,
            OrganizationalUnit,
            UserAccount,
        )
        .join(
            VisitorProfile,
            VisitorProfile.person_id == Visit.visitor_person_id,
        )
        .join(
            visitor_person,
            visitor_person.id == Visit.visitor_person_id,
        )
        .join(
            ExternalOrganization,
            ExternalOrganization.id == Visit.organization_id,
        )
        .outerjoin(
            EmployeeProfile,
            EmployeeProfile.person_id == Visit.host_employee_id,
        )
        .outerjoin(
            host_person,
            host_person.id == Visit.host_employee_id,
        )
        .outerjoin(
            OrganizationalUnit,
            OrganizationalUnit.id == Visit.host_unit_id,
        )
        .outerjoin(
            UserAccount,
            UserAccount.id == Visit.created_by,
        )
    )

    return statement, visitor_person, host_person


def _visit_dict(
    visit: Visit,
    visitor_profile: VisitorProfile,
    visitor_person: Person,
    organization: ExternalOrganization,
    host_profile: EmployeeProfile | None,
    host_person: Person | None,
    host_unit: OrganizationalUnit | None,
    creator: UserAccount | None,
) -> dict[str, Any]:
    host_employee = None
    if host_profile is not None and host_person is not None:
        host_employee = {
            "person_id": host_person.id,
            "first_name": host_person.first_name,
            "last_name": host_person.last_name,
            "matricule": host_profile.matricule,
            "job_title": host_profile.job_title,
        }

    unit_summary = None
    if host_unit is not None:
        unit_summary = {
            "id": host_unit.id,
            "code": host_unit.code,
            "name": host_unit.name,
            "unit_type": host_unit.unit_type,
        }

    creator_summary = None
    if creator is not None:
        creator_summary = {
            "id": creator.id,
            "username": creator.username,
            "role": creator.role,
        }

    return {
        "id": visit.id,
        "visitor_person_id": visit.visitor_person_id,
        "organization_id": visit.organization_id,
        "host_employee_id": visit.host_employee_id,
        "host_unit_id": visit.host_unit_id,
        "purpose": visit.purpose,
        "planned_start": visit.planned_start,
        "planned_end": visit.planned_end,
        "status": visit.status,
        "created_by": visit.created_by,
        "created_at": visit.created_at,
        "updated_at": visit.updated_at,
        "visitor": {
            "id": visitor_person.id,
            "first_name": visitor_person.first_name,
            "last_name": visitor_person.last_name,
            "cin": visitor_person.cin,
            "visitor_type": visitor_profile.visitor_type,
        },
        "organization": {
            "id": organization.id,
            "legal_name": organization.legal_name,
            "short_name": organization.short_name,
            "organization_type": organization.organization_type,
            "relationship_to_onee": organization.relationship_to_onee,
        },
        "host_employee": host_employee,
        "host_unit": unit_summary,
        "creator": creator_summary,
    }


def get_visit_or_404(db: Session, visit_id: int) -> dict[str, Any]:
    statement, _, _ = _visit_query()
    statement = statement.where(Visit.id == visit_id)

    try:
        row = db.execute(statement).one_or_none()
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter la visite dans PostgreSQL."
        ) from exc

    if row is None:
        raise NotFoundError("Visite introuvable.")

    return _visit_dict(*row)


def create_visit(db: Session, payload: VisitCreate) -> dict[str, Any]:
    _, visitor_profile = _get_active_visitor(db, payload.visitor_person_id)

    reference_date = _visit_reference_date(payload.planned_start)
    _validate_visitor_validity(visitor_profile, reference_date=reference_date)
    _validate_schedule(payload.planned_start, payload.planned_end)
    _validate_hosts(payload.host_employee_id, payload.host_unit_id)

    organization_id = payload.organization_id or visitor_profile.organization_id
    _get_active_organization(db, organization_id)

    if payload.host_employee_id is not None:
        _get_active_host_employee(
            db,
            payload.host_employee_id,
            reference_date=reference_date,
        )

    if payload.host_unit_id is not None:
        _get_active_host_unit(db, payload.host_unit_id)

    if payload.created_by is not None:
        _get_active_creator(db, payload.created_by)

    visit = Visit(
        visitor_person_id=payload.visitor_person_id,
        organization_id=organization_id,
        host_employee_id=payload.host_employee_id,
        host_unit_id=payload.host_unit_id,
        purpose=payload.purpose,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        status=VisitStatus.PLANNED.value,
        created_by=payload.created_by,
    )

    try:
        db.add(visit)
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_visit_or_404(db, visit.id)


def list_visits(
    db: Session,
    *,
    status: VisitStatus | None = None,
    visitor_person_id: int | None = None,
    organization_id: int | None = None,
    host_employee_id: int | None = None,
    host_unit_id: int | None = None,
    planned_from: datetime | None = None,
    planned_to: datetime | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if planned_from is not None and planned_to is not None and planned_to < planned_from:
        raise BusinessRuleError(
            "La fin de la période de recherche ne peut pas précéder son début."
        )

    statement, visitor_person, host_person = _visit_query()

    if status is not None:
        statement = statement.where(Visit.status == status.value)

    if visitor_person_id is not None:
        statement = statement.where(Visit.visitor_person_id == visitor_person_id)

    if organization_id is not None:
        statement = statement.where(Visit.organization_id == organization_id)

    if host_employee_id is not None:
        statement = statement.where(Visit.host_employee_id == host_employee_id)

    if host_unit_id is not None:
        statement = statement.where(Visit.host_unit_id == host_unit_id)

    if planned_from is not None:
        statement = statement.where(Visit.planned_start >= planned_from)

    if planned_to is not None:
        statement = statement.where(Visit.planned_start <= planned_to)

    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Visit.purpose.ilike(pattern),
                visitor_person.first_name.ilike(pattern),
                visitor_person.last_name.ilike(pattern),
                visitor_person.cin.ilike(pattern),
                func.concat(
                    visitor_person.first_name,
                    " ",
                    visitor_person.last_name,
                ).ilike(pattern),
                ExternalOrganization.legal_name.ilike(pattern),
                ExternalOrganization.short_name.ilike(pattern),
                host_person.first_name.ilike(pattern),
                host_person.last_name.ilike(pattern),
                OrganizationalUnit.code.ilike(pattern),
                OrganizationalUnit.name.ilike(pattern),
            )
        )

    statement = (
        statement.order_by(
            Visit.planned_start.asc().nullslast(),
            Visit.created_at.desc(),
            Visit.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    try:
        rows = db.execute(statement).all()
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de charger les visites depuis PostgreSQL."
        ) from exc

    return [_visit_dict(*row) for row in rows]


def update_visit(
    db: Session,
    visit_id: int,
    payload: VisitUpdate,
) -> dict[str, Any]:
    try:
        visit = db.get(Visit, visit_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter la visite.") from exc

    if visit is None:
        raise NotFoundError("Visite introuvable.")

    if visit.status != VisitStatus.PLANNED.value:
        raise BusinessRuleError(
            "Seule une visite au statut PLANNED peut être modifiée."
        )

    updates = payload.model_dump(exclude_unset=True)

    resulting_organization_id = updates.get("organization_id", visit.organization_id)
    resulting_host_employee_id = updates.get("host_employee_id", visit.host_employee_id)
    resulting_host_unit_id = updates.get("host_unit_id", visit.host_unit_id)
    resulting_start = updates.get("planned_start", visit.planned_start)
    resulting_end = updates.get("planned_end", visit.planned_end)

    _validate_hosts(resulting_host_employee_id, resulting_host_unit_id)
    _validate_schedule(resulting_start, resulting_end)

    _, visitor_profile = _get_active_visitor(db, visit.visitor_person_id)
    reference_date = _visit_reference_date(resulting_start)
    _validate_visitor_validity(visitor_profile, reference_date=reference_date)

    if resulting_organization_id is None:
        resulting_organization_id = visitor_profile.organization_id
    _get_active_organization(db, resulting_organization_id)

    if resulting_host_employee_id is not None:
        _get_active_host_employee(
            db,
            resulting_host_employee_id,
            reference_date=reference_date,
        )

    if resulting_host_unit_id is not None:
        _get_active_host_unit(db, resulting_host_unit_id)

    visit.organization_id = resulting_organization_id
    visit.host_employee_id = resulting_host_employee_id
    visit.host_unit_id = resulting_host_unit_id
    visit.planned_start = resulting_start
    visit.planned_end = resulting_end

    if "purpose" in updates:
        visit.purpose = updates["purpose"]

    try:
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_visit_or_404(db, visit.id)


def update_visit_status(
    db: Session,
    visit_id: int,
    payload: VisitStatusUpdate,
) -> dict[str, Any]:
    try:
        visit = db.get(Visit, visit_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter la visite.") from exc

    if visit is None:
        raise NotFoundError("Visite introuvable.")

    new_status = payload.status.value
    if visit.status == new_status:
        return get_visit_or_404(db, visit.id)

    allowed = ALLOWED_STATUS_TRANSITIONS.get(visit.status, set())
    if new_status not in allowed:
        raise BusinessRuleError(
            f"Transition de statut interdite : {visit.status} vers {new_status}."
        )

    if new_status == VisitStatus.IN_PROGRESS.value:
        # Revalider les référentiels au moment réel du début de la visite.
        _, visitor_profile = _get_active_visitor(db, visit.visitor_person_id)
        _validate_visitor_validity(visitor_profile, reference_date=date.today())
        _get_active_organization(db, visit.organization_id)

        if visit.host_employee_id is not None:
            _get_active_host_employee(
                db,
                visit.host_employee_id,
                reference_date=date.today(),
            )

        if visit.host_unit_id is not None:
            _get_active_host_unit(db, visit.host_unit_id)

    visit.status = new_status

    try:
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_visit_or_404(db, visit.id)
