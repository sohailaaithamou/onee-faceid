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
    EmployeeProfile,
    InternalAssignment,
    OrganizationalUnit,
    Person,
)
from app.schemas.employee import (
    EmployeeAssignmentCreate,
    EmployeeCreate,
    EmployeeUpdate,
    EmploymentStatus,
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

        if constraint == "uq_employee_matricule_ci":
            raise ConflictError("Un agent portant ce matricule existe déjà.") from exc

        if constraint == "uq_current_primary_assignment":
            raise ConflictError(
                "Cet agent possède déjà une affectation principale ouverte."
            ) from exc

        if "Primary assignment dates overlap" in message:
            raise ConflictError(
                "Les dates de l'affectation principale chevauchent une affectation existante."
            ) from exc

        if "Only an EMPLOYEE" in message:
            raise BusinessRuleError(
                "La personne ne possède pas un profil agent compatible avec cette affectation."
            ) from exc

        if "employee_profile" in message and "requires type EMPLOYEE" in message:
            raise BusinessRuleError(
                "Le profil agent ne peut être associé qu'à une personne de type EMPLOYEE."
            ) from exc

        raise ConflictError(
            "L'agent ne peut pas être enregistré à cause d'une contrainte de données."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enregistrement de l'agent."
    ) from exc


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


def _find_duplicate_matricule(
    db: Session,
    matricule: str,
    *,
    exclude_person_id: int | None = None,
) -> bool:
    statement = select(EmployeeProfile.person_id).where(
        func.upper(func.btrim(EmployeeProfile.matricule))
        == matricule.upper().strip()
    )

    if exclude_person_id is not None:
        statement = statement.where(EmployeeProfile.person_id != exclude_person_id)

    return db.scalar(statement.limit(1)) is not None


def _get_employee_entities(
    db: Session,
    person_id: int,
) -> tuple[Person, EmployeeProfile]:
    statement = (
        select(Person, EmployeeProfile)
        .join(EmployeeProfile, EmployeeProfile.person_id == Person.id)
        .where(Person.id == person_id, Person.person_type == "EMPLOYEE")
    )

    try:
        row = db.execute(statement).one_or_none()
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'agent dans PostgreSQL."
        ) from exc

    if row is None:
        raise NotFoundError("Agent introuvable.")

    return row[0], row[1]


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


def _base_employee_dict(
    person: Person,
    profile: EmployeeProfile,
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
        "matricule": profile.matricule,
        "hire_date": profile.hire_date,
        "end_date": profile.end_date,
        "job_title": profile.job_title,
        "employment_status": profile.employment_status,
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


def get_employee_or_404(
    db: Session,
    person_id: int,
) -> dict[str, Any]:
    person, profile = _get_employee_entities(db, person_id)
    current_assignment = _load_current_assignment(db, person_id)
    assignments = _load_assignment_history(db, person_id)

    result = _base_employee_dict(person, profile, current_assignment)
    result["assignments"] = assignments
    return result


def create_employee(
    db: Session,
    payload: EmployeeCreate,
) -> dict[str, Any]:
    _get_active_unit(db, payload.initial_assignment.organizational_unit_id)

    if _find_duplicate_cin(db, payload.cin):
        raise ConflictError("Une personne portant ce CIN existe déjà.")

    if _find_duplicate_matricule(db, payload.matricule):
        raise ConflictError("Un agent portant ce matricule existe déjà.")

    person = Person(
        first_name=payload.first_name,
        last_name=payload.last_name,
        cin=payload.cin,
        phone=payload.phone,
        email=payload.email,
        person_type="EMPLOYEE",
        active=payload.employment_status == EmploymentStatus.ACTIVE,
    )

    profile = EmployeeProfile(
        matricule=payload.matricule,
        hire_date=payload.hire_date,
        end_date=payload.end_date,
        job_title=payload.job_title,
        employment_status=payload.employment_status.value,
    )

    assignment_end_date = (
        payload.end_date
        if payload.employment_status == EmploymentStatus.ENDED
        else None
    )

    assignment = InternalAssignment(
        organizational_unit_id=payload.initial_assignment.organizational_unit_id,
        position_title=(
            payload.initial_assignment.position_title or payload.job_title
        ),
        start_date=payload.initial_assignment.start_date,
        end_date=assignment_end_date,
        is_primary=True,
    )

    try:
        db.add(person)
        db.flush()

        profile.person_id = person.id
        db.add(profile)
        db.flush()

        assignment.person_id = person.id
        db.add(assignment)

        # Un seul commit rend les trois insertions atomiques.
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_employee_or_404(db, person.id)


def list_employees(
    db: Session,
    *,
    active: bool | None = None,
    employment_status: EmploymentStatus | None = None,
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
        select(Person, EmployeeProfile, InternalAssignment, OrganizationalUnit)
        .join(EmployeeProfile, EmployeeProfile.person_id == Person.id)
        .outerjoin(InternalAssignment, current_assignment_condition)
        .outerjoin(
            OrganizationalUnit,
            OrganizationalUnit.id == InternalAssignment.organizational_unit_id,
        )
        .where(Person.person_type == "EMPLOYEE")
    )

    if active is not None:
        statement = statement.where(Person.active == active)

    if employment_status is not None:
        statement = statement.where(
            EmployeeProfile.employment_status == employment_status.value
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
                EmployeeProfile.matricule.ilike(pattern),
                func.concat(Person.first_name, " ", Person.last_name).ilike(pattern),
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
            "Impossible de charger les agents depuis PostgreSQL."
        ) from exc

    results: list[dict[str, Any]] = []
    for person, profile, assignment, unit in rows:
        current_assignment = None
        if assignment is not None and unit is not None:
            current_assignment = _assignment_dict(assignment, unit)
        results.append(_base_employee_dict(person, profile, current_assignment))

    return results


def update_employee(
    db: Session,
    person_id: int,
    payload: EmployeeUpdate,
) -> dict[str, Any]:
    person, profile = _get_employee_entities(db, person_id)
    updates = payload.model_dump(exclude_unset=True)

    if "cin" in updates and _find_duplicate_cin(
        db,
        updates["cin"],
        exclude_person_id=person_id,
    ):
        raise ConflictError("Une personne portant ce CIN existe déjà.")

    if "matricule" in updates and _find_duplicate_matricule(
        db,
        updates["matricule"],
        exclude_person_id=person_id,
    ):
        raise ConflictError("Un agent portant ce matricule existe déjà.")

    requested_status = updates.get("employment_status", profile.employment_status)
    new_status = (
        requested_status
        if isinstance(requested_status, EmploymentStatus)
        else EmploymentStatus(requested_status)
    )
    new_hire_date = updates.get("hire_date", profile.hire_date)
    new_end_date = updates.get("end_date", profile.end_date)

    if (
        profile.employment_status == EmploymentStatus.ENDED.value
        and new_status != EmploymentStatus.ENDED
    ):
        raise BusinessRuleError(
            "La réactivation d'un agent terminé nécessite un processus de réembauche distinct."
        )

    if new_status == EmploymentStatus.ENDED:
        if new_end_date is None:
            raise BusinessRuleError(
                "La date de fin est obligatoire lorsque le statut est ENDED."
            )
    elif new_end_date is not None:
        raise BusinessRuleError(
            "La date de fin doit être vide pour un agent ACTIVE ou SUSPENDED."
        )

    if new_end_date is not None and new_end_date < new_hire_date:
        raise BusinessRuleError(
            "La date de fin ne peut pas être antérieure à la date d'embauche."
        )

    assignments = list(
        db.scalars(
            select(InternalAssignment).where(
                InternalAssignment.person_id == person_id
            )
        ).all()
    )

    if any(assignment.start_date < new_hire_date for assignment in assignments):
        raise BusinessRuleError(
            "La nouvelle date d'embauche est postérieure au début d'une affectation existante."
        )

    if new_status == EmploymentStatus.ENDED and new_end_date is not None:
        if any(assignment.start_date > new_end_date for assignment in assignments):
            raise BusinessRuleError(
                "Une affectation commence après la date de fin d'emploi."
            )

        for assignment in assignments:
            if assignment.end_date is None or assignment.end_date > new_end_date:
                assignment.end_date = new_end_date

    person_fields = {"first_name", "last_name", "cin", "phone", "email"}
    profile_fields = {
        "matricule",
        "hire_date",
        "end_date",
        "job_title",
        "employment_status",
    }

    for field_name in person_fields.intersection(updates):
        setattr(person, field_name, updates[field_name])

    for field_name in profile_fields.intersection(updates):
        value = updates[field_name]
        if field_name == "employment_status" and isinstance(value, EmploymentStatus):
            value = value.value
        setattr(profile, field_name, value)

    person.active = new_status == EmploymentStatus.ACTIVE

    try:
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_employee_or_404(db, person_id)


def create_employee_assignment(
    db: Session,
    person_id: int,
    payload: EmployeeAssignmentCreate,
) -> dict[str, Any]:
    _, profile = _get_employee_entities(db, person_id)

    if profile.employment_status == EmploymentStatus.ENDED.value:
        raise BusinessRuleError(
            "Un agent dont l'emploi est terminé ne peut pas recevoir une nouvelle affectation."
        )

    _get_active_unit(db, payload.organizational_unit_id)

    if payload.start_date < profile.hire_date:
        raise BusinessRuleError(
            "La nouvelle affectation ne peut pas commencer avant la date d'embauche."
        )

    open_assignment = db.scalar(
        select(InternalAssignment)
        .where(
            InternalAssignment.person_id == person_id,
            InternalAssignment.is_primary.is_(True),
            InternalAssignment.end_date.is_(None),
        )
        .order_by(InternalAssignment.start_date.desc())
        .limit(1)
    )

    if open_assignment is not None:
        if payload.start_date <= open_assignment.start_date:
            raise BusinessRuleError(
                "La nouvelle affectation doit commencer après l'affectation principale ouverte."
            )
        open_assignment.end_date = payload.start_date - timedelta(days=1)

    new_assignment = InternalAssignment(
        person_id=person_id,
        organizational_unit_id=payload.organizational_unit_id,
        position_title=payload.position_title or profile.job_title,
        start_date=payload.start_date,
        end_date=None,
        is_primary=True,
    )
    db.add(new_assignment)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return get_employee_or_404(db, person_id)
