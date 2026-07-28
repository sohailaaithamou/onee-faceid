from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.attendance_settings import attendance_settings
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
)
from app.models import Person, PresenceEvent, RecognitionEvent, Visit
from app.schemas.presence import (
    CurrentPresenceList,
    PersonPresenceState,
    PresenceEventList,
    PresenceEventRead,
    PresenceEventType,
    PresenceFromRecognitionCreate,
    PresencePersonSummary,
    PresenceRecognitionSummary,
    PresenceRegistrationResult,
    PresenceSource,
    PresenceStatus,
    PresenceVisitSummary,
)


ACTIVE_PRESENCE_STATUSES = {
    PresenceStatus.VALID.value,
    PresenceStatus.CORRECTED.value,
}


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint = _constraint_name(exc)

        if constraint == "uq_presence_recognition_event":
            raise ConflictError(
                "Cette reconnaissance a déjà produit un événement de présence."
            ) from exc

        if constraint == "fk_presence_event_person":
            raise NotFoundError("Personne introuvable.") from exc

        if constraint == "fk_presence_event_recognition":
            raise NotFoundError(
                "Événement de reconnaissance introuvable."
            ) from exc

        if constraint == "fk_presence_event_visit":
            raise NotFoundError("Visite introuvable.") from exc

        if constraint == "chk_presence_event_source_consistency":
            raise BusinessRuleError(
                "Un pointage FACE doit être lié à une reconnaissance valide."
            ) from exc

        raise ConflictError(
            "L'événement de présence ne peut pas être enregistré."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enregistrement du pointage."
    ) from exc


def _load_presence_statement():
    return select(PresenceEvent).options(
        selectinload(PresenceEvent.person),
        selectinload(PresenceEvent.recognition_event),
        selectinload(PresenceEvent.visit),
    )


def _person_summary(person: Person) -> PresencePersonSummary:
    return PresencePersonSummary(
        id=person.id,
        first_name=person.first_name,
        last_name=person.last_name,
        person_type=person.person_type,
        active=person.active,
    )


def _recognition_summary(
    recognition: RecognitionEvent | None,
) -> PresenceRecognitionSummary | None:
    if recognition is None:
        return None

    return PresenceRecognitionSummary(
        id=recognition.id,
        captured_at=recognition.captured_at,
        decision=recognition.decision,
        similarity_score=(
            float(recognition.similarity_score)
            if recognition.similarity_score is not None
            else None
        ),
        threshold_used=(
            float(recognition.threshold_used)
            if recognition.threshold_used is not None
            else None
        ),
        device_code=recognition.device_code,
    )


def _visit_summary(visit: Visit | None) -> PresenceVisitSummary | None:
    if visit is None:
        return None

    return PresenceVisitSummary(
        id=visit.id,
        purpose=visit.purpose,
        status=visit.status,
        planned_start=visit.planned_start,
        planned_end=visit.planned_end,
    )


def _presence_read(event: PresenceEvent) -> PresenceEventRead:
    return PresenceEventRead(
        id=event.id,
        person_id=event.person_id,
        recognition_event_id=event.recognition_event_id,
        visit_id=event.visit_id,
        event_type=PresenceEventType(event.event_type),
        event_time=event.event_time,
        source=PresenceSource(event.source),
        status=PresenceStatus(event.status),
        note=event.note,
        created_by=event.created_by,
        created_at=event.created_at,
        person=_person_summary(event.person),
        recognition=_recognition_summary(event.recognition_event),
        visit=_visit_summary(event.visit),
    )


def _get_presence_model_or_404(
    db: Session,
    presence_id: int,
) -> PresenceEvent:
    statement = _load_presence_statement().where(
        PresenceEvent.id == presence_id
    )

    try:
        event = db.scalar(statement)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'événement de présence."
        ) from exc

    if event is None:
        raise NotFoundError("Événement de présence introuvable.")

    return event


def _get_recognition_or_404(
    db: Session,
    recognition_id: int,
) -> RecognitionEvent:
    statement = (
        select(RecognitionEvent)
        .options(selectinload(RecognitionEvent.matched_person))
        .where(RecognitionEvent.id == recognition_id)
    )

    try:
        recognition = db.scalar(statement)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'événement de reconnaissance."
        ) from exc

    if recognition is None:
        raise NotFoundError("Événement de reconnaissance introuvable.")

    return recognition


def _existing_presence_for_recognition(
    db: Session,
    recognition_id: int,
) -> PresenceEvent | None:
    statement = _load_presence_statement().where(
        PresenceEvent.recognition_event_id == recognition_id
    )

    try:
        return db.scalar(statement)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de vérifier si la reconnaissance a déjà été pointée."
        ) from exc


def _latest_valid_presence(
    db: Session,
    person_id: int,
) -> PresenceEvent | None:
    statement = (
        _load_presence_statement()
        .where(
            PresenceEvent.person_id == person_id,
            PresenceEvent.status.in_(ACTIVE_PRESENCE_STATUSES),
        )
        .order_by(
            PresenceEvent.event_time.desc(),
            PresenceEvent.id.desc(),
        )
        .limit(1)
    )

    try:
        return db.scalar(statement)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter le dernier pointage de la personne."
        ) from exc


def _validate_recognition(recognition: RecognitionEvent) -> Person:
    if recognition.decision != "MATCHED":
        raise BusinessRuleError(
            "Seule une reconnaissance MATCHED peut produire un pointage."
        )

    if recognition.matched_person_id is None or recognition.matched_person is None:
        raise BusinessRuleError(
            "La reconnaissance MATCHED ne contient aucune personne."
        )

    person = recognition.matched_person
    if not person.active:
        raise BusinessRuleError(
            "La personne reconnue est désactivée et ne peut pas pointer."
        )

    return person


def _next_event_type(last_event: PresenceEvent | None) -> PresenceEventType:
    if last_event is None or last_event.event_type == PresenceEventType.EXIT.value:
        return PresenceEventType.ENTRY
    return PresenceEventType.EXIT


def _validate_chronology_and_cooldown(
    recognition: RecognitionEvent,
    last_event: PresenceEvent | None,
) -> None:
    if last_event is None:
        return

    recognition_time = recognition.captured_at
    last_time = last_event.event_time

    if recognition_time.tzinfo is None:
        recognition_time = recognition_time.replace(tzinfo=timezone.utc)
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=timezone.utc)

    delta = recognition_time - last_time
    if delta.total_seconds() < 0:
        raise BusinessRuleError(
            "Cette reconnaissance est antérieure au dernier pointage enregistré."
        )

    cooldown = attendance_settings.cooldown_seconds
    if cooldown > 0 and delta < timedelta(seconds=cooldown):
        remaining = max(1, cooldown - int(delta.total_seconds()))
        raise ConflictError(
            "Pointage trop rapproché. "
            f"Attendez encore environ {remaining} seconde(s)."
        )


def _resolve_visit(
    db: Session,
    *,
    person: Person,
    requested_visit_id: int | None,
    last_event: PresenceEvent | None,
    event_type: PresenceEventType,
) -> Visit | None:
    if person.person_type == "EMPLOYEE":
        if requested_visit_id is not None:
            raise BusinessRuleError(
                "Un agent ONEE ne doit pas être lié à une visite externe."
            )
        return None

    visit_id = requested_visit_id
    if (
        visit_id is None
        and event_type == PresenceEventType.EXIT
        and last_event is not None
    ):
        visit_id = last_event.visit_id

    if visit_id is None:
        if attendance_settings.require_visit_for_visitors:
            raise BusinessRuleError(
                "Un visiteur doit être lié à une visite avant son pointage."
            )
        return None

    try:
        visit = db.get(Visit, visit_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter la visite associée au pointage."
        ) from exc

    if visit is None:
        raise NotFoundError("Visite introuvable.")

    if visit.visitor_person_id != person.id:
        raise BusinessRuleError(
            "La visite sélectionnée n'appartient pas à la personne reconnue."
        )

    if event_type == PresenceEventType.ENTRY:
        if visit.status not in {"PLANNED", "IN_PROGRESS"}:
            raise BusinessRuleError(
                "Une entrée visiteur exige une visite PLANNED ou IN_PROGRESS."
            )
    else:
        if last_event is None or last_event.visit_id != visit.id:
            raise BusinessRuleError(
                "La sortie doit utiliser la même visite que l'entrée en cours."
            )
        if visit.status != "IN_PROGRESS":
            raise BusinessRuleError(
                "Une sortie visiteur exige une visite au statut IN_PROGRESS."
            )

    return visit


def _update_visit_status_for_presence(
    visit: Visit | None,
    event_type: PresenceEventType,
) -> None:
    if visit is None or not attendance_settings.auto_update_visit_status:
        return

    if event_type == PresenceEventType.ENTRY and visit.status == "PLANNED":
        visit.status = "IN_PROGRESS"
    elif event_type == PresenceEventType.EXIT and visit.status == "IN_PROGRESS":
        visit.status = "COMPLETED"


def create_presence_from_recognition(
    db: Session,
    recognition_id: int,
    payload: PresenceFromRecognitionCreate,
) -> PresenceRegistrationResult:
    existing = _existing_presence_for_recognition(db, recognition_id)
    if existing is not None:
        return PresenceRegistrationResult(
            message="Cette reconnaissance avait déjà produit ce pointage.",
            created=False,
            presence=_presence_read(existing),
        )

    recognition = _get_recognition_or_404(db, recognition_id)
    person = _validate_recognition(recognition)
    last_event = _latest_valid_presence(db, person.id)
    _validate_chronology_and_cooldown(recognition, last_event)

    event_type = _next_event_type(last_event)
    visit = _resolve_visit(
        db,
        person=person,
        requested_visit_id=payload.visit_id,
        last_event=last_event,
        event_type=event_type,
    )
    _update_visit_status_for_presence(visit, event_type)

    note = payload.note.strip() if payload.note else None
    if note == "":
        note = None

    presence = PresenceEvent(
        person_id=person.id,
        recognition_event_id=recognition.id,
        visit_id=(visit.id if visit is not None else None),
        event_type=event_type.value,
        event_time=recognition.captured_at,
        source=PresenceSource.FACE.value,
        status=PresenceStatus.VALID.value,
        note=note,
        created_by=None,
    )

    try:
        db.add(presence)
        db.flush()
        presence_id = presence.id
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
        raise AssertionError("unreachable")

    created = _get_presence_model_or_404(db, presence_id)
    action = "Entrée" if event_type == PresenceEventType.ENTRY else "Sortie"
    return PresenceRegistrationResult(
        message=f"{action} enregistrée pour {person.first_name} {person.last_name}.",
        created=True,
        presence=_presence_read(created),
    )


def get_presence_event(
    db: Session,
    presence_id: int,
) -> PresenceEventRead:
    return _presence_read(_get_presence_model_or_404(db, presence_id))


def list_presence_events(
    db: Session,
    *,
    person_id: int | None = None,
    event_type: PresenceEventType | None = None,
    source: PresenceSource | None = None,
    status: PresenceStatus | None = None,
    event_from: datetime | None = None,
    event_to: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> PresenceEventList:
    if event_from is not None and event_to is not None and event_to < event_from:
        raise BusinessRuleError(
            "La fin de la période ne peut pas précéder son début."
        )

    filters = []
    if person_id is not None:
        filters.append(PresenceEvent.person_id == person_id)
    if event_type is not None:
        filters.append(PresenceEvent.event_type == event_type.value)
    if source is not None:
        filters.append(PresenceEvent.source == source.value)
    if status is not None:
        filters.append(PresenceEvent.status == status.value)
    if event_from is not None:
        filters.append(PresenceEvent.event_time >= event_from)
    if event_to is not None:
        filters.append(PresenceEvent.event_time <= event_to)

    statement = (
        _load_presence_statement()
        .where(*filters)
        .order_by(
            PresenceEvent.event_time.desc(),
            PresenceEvent.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    count_statement = select(func.count(PresenceEvent.id)).where(*filters)

    try:
        items = list(db.scalars(statement).all())
        total = int(db.scalar(count_statement) or 0)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'historique des présences."
        ) from exc

    return PresenceEventList(
        items=[_presence_read(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


def get_current_presence(
    db: Session,
) -> CurrentPresenceList:
    ranked = (
        select(
            PresenceEvent.id.label("presence_id"),
            func.row_number()
            .over(
                partition_by=PresenceEvent.person_id,
                order_by=(
                    PresenceEvent.event_time.desc(),
                    PresenceEvent.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .where(PresenceEvent.status.in_(ACTIVE_PRESENCE_STATUSES))
        .subquery()
    )

    statement = (
        _load_presence_statement()
        .join(ranked, ranked.c.presence_id == PresenceEvent.id)
        .where(
            ranked.c.row_number == 1,
            PresenceEvent.event_type == PresenceEventType.ENTRY.value,
        )
        .order_by(PresenceEvent.event_time.desc(), PresenceEvent.id.desc())
    )

    try:
        items = list(db.scalars(statement).all())
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter les personnes actuellement présentes."
        ) from exc

    return CurrentPresenceList(
        items=[_presence_read(item) for item in items],
        total=len(items),
    )


def get_person_presence_state(
    db: Session,
    person_id: int,
) -> PersonPresenceState:
    try:
        person = db.get(Person, person_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter la personne."
        ) from exc

    if person is None:
        raise NotFoundError("Personne introuvable.")

    last_event = _latest_valid_presence(db, person_id)
    return PersonPresenceState(
        person=_person_summary(person),
        is_inside=(
            last_event is not None
            and last_event.event_type == PresenceEventType.ENTRY.value
        ),
        last_event=(
            _presence_read(last_event)
            if last_event is not None
            else None
        ),
    )
