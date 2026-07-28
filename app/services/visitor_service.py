from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
)
from app.models import (
    ExternalOrganization,
    InternalAssignment,
    OrganizationalUnit,
    Person,
    VisitorProfile,
)
from app.schemas.visitor import (
    InternAssignmentCreate,
    VisitorCreate,
    VisitorType,
    VisitorUpdate,
)


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _database_message(exc: IntegrityError) -> str:
    diagnostic = getattr(exc.orig, "diag", None)
    message = getattr(diagnostic, "message_primary", None)
    return str(message or exc.orig)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint = _constraint_name(exc)
        message = _database_message(exc)

        if constraint == "uq_person_cin_ci":
            raise ConflictError("Une personne portant ce CIN existe déjà.") from exc

        if constraint == "uq_current_primary_assignment":
            raise ConflictError(
                "Ce stagiaire possède déjà une affectation principale ouverte."
            ) from exc

        if "Primary assignment dates overlap" in message:
            raise ConflictError(
                "Les dates de l'affectation chevauchent une affectation principale existante."
            ) from exc

        if "Intern assignment dates must stay inside" in message:
            raise BusinessRuleError(
                "Les dates de l'affectation doivent rester dans la période du stage."
            ) from exc

        if "Only an EMPLOYEE with a profile or an INTERN" in message:
            raise BusinessRuleError(
                "Seul un stagiaire peut recevoir une affectation interne dans ce module."
            ) from exc

        if "visitor_profile" in message and "requires type VISITOR" in message:
            raise BusinessRuleError(
                "Le profil visiteur ne peut être associé qu'à une personne de type VISITOR."
            ) from exc

        raise ConflictError(
            "Le visiteur ne peut pas être enregistré à cause d'une contrainte de données."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enregistrement du visiteur."
    ) from exc


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


def _get_active_unit(db: Session, unit_id: int) -> OrganizationalUnit:
    try:
        unit = db.get(OrganizationalUnit, unit_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'unité organisationnelle."
        ) from exc

    if unit is None:
        raise NotFoundError("Unité organisationnelle introuvable.")

    if not unit.active:
        raise BusinessRuleError(
            "L'unité organisationnelle est désactivée et ne peut pas être utilisée."
        )

    return unit


def _find_duplicate_cin(
    db: Session,
    cin: str | None,
    *,
    exclude_person_id: int | None = None,
) -> bool:
    if cin is None:
        return False

    statement = select(Person.id).where(
        func.upper(func.btrim(Person.cin)) == cin.upper().strip()
    )

    if exclude_person_id is not None:
        statement = statement.where(Person.id != exclude_person_id)

    return db.scalar(statement.limit(1)) is not None


def _get_visitor_entities(
    db: Session,
    person_id: int,
) -> tuple[Person, VisitorProfile, ExternalOrganization]:
    statement = (
        select(Person, VisitorProfile, ExternalOrganization)
        .join(VisitorProfile, VisitorProfile.person_id == Person.id)
        .join(
            ExternalOrganization,
            ExternalOrganization.id == VisitorProfile.organization_id,
        )
        .where(Person.id == person_id, Person.person_type == "VISITOR")
    )

    try:
        row = db.execute(statement).one_or_none()
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter le visiteur dans PostgreSQL."
        ) from exc

    if row is None:
        raise NotFoundError("Visiteur introuvable.")

    return row[0], row[1], row[2]


def _organization_dict(
    organization: ExternalOrganization,
) -> dict[str, Any]:
    return {
        "id": organization.id,
        "legal_name": organization.legal_name,
        "short_name": organization.short_name,
        "organization_type": organization.organization_type,
        "relationship_to_onee": organization.relationship_to_onee,
        "city": organization.city,
    }


def _assignment_dict(
    assignment: InternalAssignment,
    unit: OrganizationalUnit,
) -> dict[str, Any]:
    return {
        "id": assignment.id,
        "organizational_unit_id": assignment.organizational_unit_id,
        "position_title": assignment.position_title,
        "start_date": assignment.start_date,
        "end_date": assignment.end_date,
        "is_primary": assignment.is_primary,
        "organizational_unit": {
            "id": unit.id,
            "code": unit.code,
            "name": unit.name,
            "unit_type": unit.unit_type,
        },
    }


def _base_visitor_dict(
    person: Person,
    profile: VisitorProfile,
    organization: ExternalOrganization,
    current_assignment: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "id": person.id,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "cin": person.cin,
        "phone": person.phone,
        "email": person.email,
        "active": person.active,
        "created_at": person.created_at,
        "updated_at": person.updated_at,
        "visitor_type": profile.visitor_type,
        "organization_id": profile.organization_id,
        "valid_from": profile.valid_from,
        "valid_until": profile.valid_until,
        "profile_active": profile.active,
        "organization": _organization_dict(organization),
        "current_assignment": current_assignment,
    }


def _load_current_assignment(
    db: Session,
    person_id: int,
    *,
    reference_date: date | None = None,
) -> dict[str, Any] | None:
    reference_date = reference_date or date.today()

    statement = (
        select(InternalAssignment, OrganizationalUnit)
        .join(
            OrganizationalUnit,
            OrganizationalUnit.id == InternalAssignment.organizational_unit_id,
        )
        .where(
            InternalAssignment.person_id == person_id,
            InternalAssignment.is_primary.is_(True),
            InternalAssignment.start_date <= reference_date,
            or_(
                InternalAssignment.end_date.is_(None),
                InternalAssignment.end_date >= reference_date,
            ),
        )
        .order_by(InternalAssignment.start_date.desc(), InternalAssignment.id.desc())
        .limit(1)
    )

    row = db.execute(statement).one_or_none()
    if row is None:
        return None

    return _assignment_dict(row[0], row[1])


def _load_assignment_history(
    db: Session,
    person_id: int,
) -> list[dict[str, Any]]:
    statement = (
        select(InternalAssignment, OrganizationalUnit)
        .join(
            OrganizationalUnit,
            OrganizationalUnit.id == InternalAssignment.organizational_unit_id,
        )
        .where(InternalAssignment.person_id == person_id)
        .order_by(InternalAssignment.start_date.desc(), InternalAssignment.id.desc())
    )

    rows = db.execute(statement).all()
    return [_assignment_dict(assignment, unit) for assignment, unit in rows]


def get_visitor_or_404(
    db: Session,
    person_id: int,
) -> dict[str, Any]:
    person, profile, organization = _get_visitor_entities(db, person_id)
    current_assignment = _load_current_assignment(db, person_id)
    assignments = _load_assignment_history(db, person_id)

    result = _base_visitor_dict(
        person,
        profile,
        organization,
        current_assignment,
    )
    result["assignments"] = assignments
    return result


def create_visitor(
    db: Session,
    payload: VisitorCreate,
) -> dict[str, Any]:
    organization = _get_active_organization(db, payload.organization_id)

    if _find_duplicate_cin(db, payload.cin):
        raise ConflictError("Une personne portant ce CIN existe déjà.")

    assignment_unit: OrganizationalUnit | None = None
    assignment_end: date | None = None

    if payload.visitor_type == VisitorType.INTERN:
        if payload.initial_assignment is None:
            raise BusinessRuleError(
                "Une affectation initiale est obligatoire pour un stagiaire."
            )

        assignment_unit = _get_active_unit(
            db,
            payload.initial_assignment.organizational_unit_id,
        )
        assignment_end = payload.initial_assignment.end_date or payload.valid_until

        if payload.valid_from is None or payload.valid_until is None:
            raise BusinessRuleError(
                "Les dates de validité sont obligatoires pour un stagiaire."
            )

        if payload.initial_assignment.start_date < payload.valid_from:
            raise BusinessRuleError(
                "L'affectation ne peut pas commencer avant le début du stage."
            )

        if assignment_end is None or assignment_end > payload.valid_until:
            raise BusinessRuleError(
                "L'affectation doit terminer au plus tard à la fin du stage."
            )

    person = Person(
        first_name=payload.first_name,
        last_name=payload.last_name,
        cin=payload.cin,
        phone=payload.phone,
        email=payload.email,
        person_type="VISITOR",
        active=payload.active,
    )

    profile = VisitorProfile(
        visitor_type=payload.visitor_type.value,
        organization_id=organization.id,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        active=payload.active,
    )

    try:
        db.add(person)
        db.flush()

        profile.person_id = person.id
        db.add(profile)
        db.flush()

        if payload.visitor_type == VisitorType.INTERN:
            assert payload.initial_assignment is not None
            assert assignment_unit is not None
            assert assignment_end is not None

            assignment = InternalAssignment(
                person_id=person.id,
                organizational_unit_id=assignment_unit.id,
                position_title=(
                    payload.initial_assignment.position_title or "Stagiaire"
                ),
                start_date=payload.initial_assignment.start_date,
                end_date=assignment_end,
                is_primary=True,
            )
            db.add(assignment)

        # PERSON, VISITOR_PROFILE et l'affectation éventuelle sont atomiques.
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_visitor_or_404(db, person.id)


def list_visitors(
    db: Session,
    *,
    active: bool | None = None,
    visitor_type: VisitorType | None = None,
    organization_id: int | None = None,
    organizational_unit_id: int | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    today = date.today()

    current_assignment_condition = and_(
        InternalAssignment.person_id == Person.id,
        InternalAssignment.is_primary.is_(True),
        InternalAssignment.start_date <= today,
        or_(
            InternalAssignment.end_date.is_(None),
            InternalAssignment.end_date >= today,
        ),
    )

    statement = (
        select(
            Person,
            VisitorProfile,
            ExternalOrganization,
            InternalAssignment,
            OrganizationalUnit,
        )
        .join(VisitorProfile, VisitorProfile.person_id == Person.id)
        .join(
            ExternalOrganization,
            ExternalOrganization.id == VisitorProfile.organization_id,
        )
        .outerjoin(InternalAssignment, current_assignment_condition)
        .outerjoin(
            OrganizationalUnit,
            OrganizationalUnit.id == InternalAssignment.organizational_unit_id,
        )
        .where(Person.person_type == "VISITOR")
    )

    if active is not None:
        statement = statement.where(
            Person.active == active,
            VisitorProfile.active == active,
        )

    if visitor_type is not None:
        statement = statement.where(
            VisitorProfile.visitor_type == visitor_type.value
        )

    if organization_id is not None:
        statement = statement.where(
            VisitorProfile.organization_id == organization_id
        )

    if organizational_unit_id is not None:
        statement = statement.where(
            InternalAssignment.organizational_unit_id == organizational_unit_id
        )

    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Person.first_name.ilike(pattern),
                Person.last_name.ilike(pattern),
                Person.cin.ilike(pattern),
                func.concat(Person.first_name, " ", Person.last_name).ilike(pattern),
                ExternalOrganization.legal_name.ilike(pattern),
                ExternalOrganization.short_name.ilike(pattern),
            )
        )

    statement = (
        statement.order_by(
            func.lower(Person.last_name),
            func.lower(Person.first_name),
            Person.id,
        )
        .offset(offset)
        .limit(limit)
    )

    try:
        rows = db.execute(statement).all()
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de charger les visiteurs depuis PostgreSQL."
        ) from exc

    results: list[dict[str, Any]] = []
    for person, profile, organization, assignment, unit in rows:
        current_assignment = None
        if assignment is not None and unit is not None:
            current_assignment = _assignment_dict(assignment, unit)

        results.append(
            _base_visitor_dict(
                person,
                profile,
                organization,
                current_assignment,
            )
        )

    return results


def update_visitor(
    db: Session,
    person_id: int,
    payload: VisitorUpdate,
) -> dict[str, Any]:
    person, profile, _ = _get_visitor_entities(db, person_id)
    updates = payload.model_dump(exclude_unset=True)

    if "cin" in updates and _find_duplicate_cin(
        db,
        updates["cin"],
        exclude_person_id=person_id,
    ):
        raise ConflictError("Une personne portant ce CIN existe déjà.")

    if "organization_id" in updates:
        _get_active_organization(db, updates["organization_id"])

    new_valid_from = updates.get("valid_from", profile.valid_from)
    new_valid_until = updates.get("valid_until", profile.valid_until)

    if profile.visitor_type == VisitorType.INTERN.value:
        if new_valid_from is None or new_valid_until is None:
            raise BusinessRuleError(
                "Les dates de début et de fin restent obligatoires pour un stagiaire."
            )

        if new_valid_until < new_valid_from:
            raise BusinessRuleError(
                "La date de fin du stage ne peut pas être antérieure à sa date de début."
            )

        assignments = list(
            db.scalars(
                select(InternalAssignment).where(
                    InternalAssignment.person_id == person_id
                )
            ).all()
        )

        for assignment in assignments:
            if (
                assignment.start_date < new_valid_from
                or assignment.end_date is None
                or assignment.end_date > new_valid_until
            ):
                raise BusinessRuleError(
                    "Modifiez d'abord les affectations : elles doivent rester dans la nouvelle période du stage."
                )
    else:
        if (new_valid_from is None) != (new_valid_until is None):
            raise BusinessRuleError(
                "Fournissez les deux dates de validité ou laissez-les toutes les deux vides."
            )

        if (
            new_valid_from is not None
            and new_valid_until is not None
            and new_valid_until < new_valid_from
        ):
            raise BusinessRuleError(
                "La date de fin de validité ne peut pas être antérieure à sa date de début."
            )

    person_fields = {"first_name", "last_name", "cin", "phone", "email"}
    profile_fields = {"organization_id", "valid_from", "valid_until", "active"}

    for field_name in person_fields.intersection(updates):
        setattr(person, field_name, updates[field_name])

    for field_name in profile_fields.intersection(updates):
        setattr(profile, field_name, updates[field_name])

    if "active" in updates:
        person.active = updates["active"]
        profile.active = updates["active"]

    try:
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_visitor_or_404(db, person_id)


def create_intern_assignment(
    db: Session,
    person_id: int,
    payload: InternAssignmentCreate,
) -> dict[str, Any]:
    person, profile, _ = _get_visitor_entities(db, person_id)

    if profile.visitor_type != VisitorType.INTERN.value:
        raise BusinessRuleError(
            "Seul un visiteur de type INTERN peut recevoir une affectation interne."
        )

    if not person.active or not profile.active:
        raise BusinessRuleError(
            "Un stagiaire désactivé ne peut pas recevoir une nouvelle affectation."
        )

    if profile.valid_from is None or profile.valid_until is None:
        raise BusinessRuleError(
            "La période de validité du stage est incomplète."
        )

    _get_active_unit(db, payload.organizational_unit_id)

    assignment_end = payload.end_date or profile.valid_until

    if payload.start_date < profile.valid_from:
        raise BusinessRuleError(
            "L'affectation ne peut pas commencer avant le début du stage."
        )

    if assignment_end > profile.valid_until:
        raise BusinessRuleError(
            "L'affectation ne peut pas terminer après la fin du stage."
        )

    latest_assignment = db.scalar(
        select(InternalAssignment)
        .where(
            InternalAssignment.person_id == person_id,
            InternalAssignment.is_primary.is_(True),
        )
        .order_by(
            InternalAssignment.start_date.desc(),
            InternalAssignment.id.desc(),
        )
        .limit(1)
    )

    if latest_assignment is not None:
        if payload.start_date <= latest_assignment.start_date:
            raise BusinessRuleError(
                "La nouvelle affectation doit commencer après la dernière affectation."
            )

        if (
            latest_assignment.end_date is None
            or latest_assignment.end_date >= payload.start_date
        ):
            latest_assignment.end_date = payload.start_date - timedelta(days=1)

    new_assignment = InternalAssignment(
        person_id=person_id,
        organizational_unit_id=payload.organizational_unit_id,
        position_title=payload.position_title or "Stagiaire",
        start_date=payload.start_date,
        end_date=assignment_end,
        is_primary=True,
    )
    db.add(new_assignment)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_visitor_or_404(db, person_id)
