from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from time import perf_counter

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
)
from app.models import Person, RecognitionEvent
from app.schemas.recognition import (
    RecognitionAttemptResult,
    RecognitionCandidate,
    RecognitionDecision,
    RecognitionDiagnostic,
    RecognitionEventList,
    RecognitionEventRead,
    RecognitionIndexStatus,
    RecognitionPersonSummary,
)
from app.vision import (
    FaceEngine,
    FaceProcessingError,
    get_face_embedding_index,
    get_face_engine,
)
from app.vision.settings import face_settings


@dataclass(frozen=True, slots=True)
class RecognitionUpload:
    filename: str
    content_type: str | None
    content: bytes


@dataclass(frozen=True, slots=True)
class _BestPersonMatch:
    person_id: int
    first_name: str
    last_name: str
    person_type: str
    similarity_score: float
    embedding_id: int
    capture_label: str | None


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint = _constraint_name(exc)

        if constraint == "fk_recognition_event_person":
            raise NotFoundError("La personne reconnue est introuvable.") from exc

        if constraint == "chk_recognition_person_consistency":
            raise BusinessRuleError(
                "Le résultat de reconnaissance ne respecte pas les règles MATCHED/UNKNOWN."
            ) from exc

        if constraint in {
            "chk_recognition_similarity",
            "chk_recognition_threshold",
        }:
            raise BusinessRuleError(
                "Le score ou le seuil de reconnaissance doit être compris entre -1 et 1."
            ) from exc

        raise ConflictError(
            "L'événement de reconnaissance ne peut pas être enregistré."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant la reconnaissance."
    ) from exc


def _person_summary(person: Person | None) -> RecognitionPersonSummary | None:
    if person is None:
        return None

    return RecognitionPersonSummary(
        id=person.id,
        first_name=person.first_name,
        last_name=person.last_name,
        person_type=person.person_type,
        active=person.active,
    )


def _event_read(event: RecognitionEvent) -> RecognitionEventRead:
    return RecognitionEventRead(
        id=event.id,
        matched_person_id=event.matched_person_id,
        captured_at=event.captured_at,
        decision=RecognitionDecision(event.decision),
        similarity_score=(
            float(event.similarity_score)
            if event.similarity_score is not None
            else None
        ),
        threshold_used=(
            float(event.threshold_used)
            if event.threshold_used is not None
            else None
        ),
        liveness_score=(
            float(event.liveness_score)
            if event.liveness_score is not None
            else None
        ),
        model_name=event.model_name,
        model_version=event.model_version,
        processing_time_ms=event.processing_time_ms,
        device_code=event.device_code,
        snapshot_path=event.snapshot_path,
        error_message=event.error_message,
        matched_person=_person_summary(event.matched_person),
    )


def _validate_upload(upload: RecognitionUpload) -> None:
    allowed_content_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }

    if upload.content_type and upload.content_type.lower() not in allowed_content_types:
        raise BusinessRuleError(
            "Format non accepté. Utilisez une image JPEG, PNG ou WebP."
        )

    if not upload.content:
        raise BusinessRuleError("Le fichier image est vide.")

    if len(upload.content) > face_settings.max_upload_bytes:
        maximum_mb = face_settings.max_upload_bytes / (1024 * 1024)
        raise BusinessRuleError(
            f"Le fichier dépasse la limite de {maximum_mb:.0f} Mo."
        )


def _sanitize_device_code(device_code: str | None) -> str | None:
    if device_code is None:
        return None

    value = device_code.strip()
    if not value:
        return None
    if len(value) > 80:
        raise BusinessRuleError(
            "Le code de l'appareil ne doit pas dépasser 80 caractères."
        )
    return value


def _decimal_score(value: float | None) -> Decimal | None:
    if value is None:
        return None
    bounded = max(-1.0, min(1.0, value))
    return Decimal(f"{bounded:.6f}")


def _decision_for_face_error(message: str) -> RecognitionDecision:
    lowered = message.lower()
    if "plusieurs visages" in lowered:
        return RecognitionDecision.MULTIPLE_FACES
    return RecognitionDecision.LOW_QUALITY


def _create_event(
    db: Session,
    *,
    decision: RecognitionDecision,
    matched_person_id: int | None,
    similarity_score: float | None,
    threshold_used: float | None,
    processing_time_ms: int,
    device_code: str | None,
    error_message: str | None,
) -> RecognitionEvent:
    event = RecognitionEvent(
        matched_person_id=matched_person_id,
        decision=decision.value,
        similarity_score=_decimal_score(similarity_score),
        threshold_used=_decimal_score(threshold_used),
        liveness_score=None,
        model_name="SFace",
        model_version=face_settings.model_version,
        processing_time_ms=max(0, processing_time_ms),
        device_code=device_code,
        snapshot_path=None,
        error_message=error_message,
    )
    db.add(event)

    try:
        db.flush()
        db.commit()
        statement = (
            select(RecognitionEvent)
            .options(selectinload(RecognitionEvent.matched_person))
            .where(RecognitionEvent.id == event.id)
        )
        created = db.scalar(statement)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
        raise AssertionError("unreachable")

    if created is None:
        raise DatabaseOperationError(
            "L'événement a été créé mais ne peut pas être relu."
        )
    return created


def _compare_with_index(
    query_embedding: list[float],
    indexed_items,
) -> list[_BestPersonMatch]:
    query_vector = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
    query_norm = float(np.linalg.norm(query_vector))
    if query_vector.size != 128 or query_norm <= 1e-12:
        raise FaceProcessingError("L'embedding de la capture est invalide.")
    query_vector = query_vector / query_norm

    best_by_person: dict[int, _BestPersonMatch] = {}

    for item in indexed_items:
        score = float(np.dot(query_vector, item.vector))
        score = max(-1.0, min(1.0, score))

        current = best_by_person.get(item.person_id)
        if current is None or score > current.similarity_score:
            best_by_person[item.person_id] = _BestPersonMatch(
                person_id=item.person_id,
                first_name=item.first_name,
                last_name=item.last_name,
                person_type=item.person_type,
                similarity_score=score,
                embedding_id=item.embedding_id,
                capture_label=item.capture_label,
            )

    return sorted(
        best_by_person.values(),
        key=lambda candidate: candidate.similarity_score,
        reverse=True,
    )


def recognize_face(
    db: Session,
    upload: RecognitionUpload,
    *,
    device_code: str | None = None,
    refresh_index: bool = False,
    engine: FaceEngine | None = None,
) -> RecognitionAttemptResult:
    started_at = perf_counter()
    _validate_upload(upload)
    cleaned_device_code = _sanitize_device_code(device_code)
    face_engine = engine or get_face_engine()

    try:
        extracted = face_engine.extract(upload.content)
    except FaceProcessingError as exc:
        elapsed_ms = int(round((perf_counter() - started_at) * 1000))
        decision = _decision_for_face_error(str(exc))
        event = _create_event(
            db,
            decision=decision,
            matched_person_id=None,
            similarity_score=None,
            threshold_used=None,
            processing_time_ms=elapsed_ms,
            device_code=cleaned_device_code,
            error_message=str(exc),
        )
        return RecognitionAttemptResult(
            message="La tentative a été enregistrée, mais le visage n'est pas exploitable.",
            event=_event_read(event),
            diagnostic=None,
            candidates=[],
            indexed_embeddings=0,
            indexed_persons=0,
        )
    except RuntimeError as exc:
        elapsed_ms = int(round((perf_counter() - started_at) * 1000))
        event = _create_event(
            db,
            decision=RecognitionDecision.ERROR,
            matched_person_id=None,
            similarity_score=None,
            threshold_used=None,
            processing_time_ms=elapsed_ms,
            device_code=cleaned_device_code,
            error_message=str(exc),
        )
        return RecognitionAttemptResult(
            message="La tentative a été enregistrée avec une erreur du moteur facial.",
            event=_event_read(event),
            diagnostic=None,
            candidates=[],
            indexed_embeddings=0,
            indexed_persons=0,
        )

    index = get_face_embedding_index()
    snapshot = index.get(db, force_refresh=refresh_index)

    diagnostic = RecognitionDiagnostic(
        detection_score=extracted.detection_score,
        sharpness_score=extracted.sharpness_score,
        face_width=extracted.face_width,
        face_height=extracted.face_height,
        quality_score=extracted.quality_score,
    )

    if not snapshot.items:
        elapsed_ms = int(round((perf_counter() - started_at) * 1000))
        event = _create_event(
            db,
            decision=RecognitionDecision.ERROR,
            matched_person_id=None,
            similarity_score=None,
            threshold_used=None,
            processing_time_ms=elapsed_ms,
            device_code=cleaned_device_code,
            error_message=(
                "Aucun embedding actif compatible avec la version du modèle n'est disponible."
            ),
        )
        return RecognitionAttemptResult(
            message="Aucune personne enrôlée n'est disponible dans l'index facial.",
            event=_event_read(event),
            diagnostic=diagnostic,
            candidates=[],
            indexed_embeddings=0,
            indexed_persons=0,
        )

    ranked = _compare_with_index(extracted.embedding, snapshot.items)
    best = ranked[0] if ranked else None
    threshold = face_settings.recognition_threshold

    if best is not None and best.similarity_score >= threshold:
        decision = RecognitionDecision.MATCHED
        matched_person_id = best.person_id
        message = (
            f"Personne reconnue : {best.first_name} {best.last_name}."
        )
    else:
        decision = RecognitionDecision.UNKNOWN
        matched_person_id = None
        message = "Visage détecté, mais aucune personne ne dépasse le seuil de reconnaissance."

    candidates = [
        RecognitionCandidate(
            person_id=item.person_id,
            first_name=item.first_name,
            last_name=item.last_name,
            person_type=item.person_type,
            similarity_score=round(item.similarity_score, 6),
            embedding_id=item.embedding_id,
            capture_label=item.capture_label,
        )
        for item in ranked[: face_settings.recognition_top_candidates]
    ]

    elapsed_ms = int(round((perf_counter() - started_at) * 1000))
    event = _create_event(
        db,
        decision=decision,
        matched_person_id=matched_person_id,
        similarity_score=(best.similarity_score if best is not None else None),
        threshold_used=threshold,
        processing_time_ms=elapsed_ms,
        device_code=cleaned_device_code,
        error_message=None,
    )

    return RecognitionAttemptResult(
        message=message,
        event=_event_read(event),
        diagnostic=diagnostic,
        candidates=candidates,
        indexed_embeddings=len(snapshot.items),
        indexed_persons=snapshot.persons_count,
    )


def get_recognition_event(
    db: Session,
    recognition_id: int,
) -> RecognitionEventRead:
    statement = (
        select(RecognitionEvent)
        .options(selectinload(RecognitionEvent.matched_person))
        .where(RecognitionEvent.id == recognition_id)
    )

    try:
        event = db.scalar(statement)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'événement de reconnaissance."
        ) from exc

    if event is None:
        raise NotFoundError("Événement de reconnaissance introuvable.")

    return _event_read(event)


def list_recognition_events(
    db: Session,
    *,
    decision: RecognitionDecision | None = None,
    matched_person_id: int | None = None,
    captured_from: datetime | None = None,
    captured_to: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> RecognitionEventList:
    filters = []
    if decision is not None:
        filters.append(RecognitionEvent.decision == decision.value)
    if matched_person_id is not None:
        filters.append(RecognitionEvent.matched_person_id == matched_person_id)
    if captured_from is not None:
        filters.append(RecognitionEvent.captured_at >= captured_from)
    if captured_to is not None:
        filters.append(RecognitionEvent.captured_at <= captured_to)

    statement = (
        select(RecognitionEvent)
        .options(selectinload(RecognitionEvent.matched_person))
        .where(*filters)
        .order_by(RecognitionEvent.captured_at.desc(), RecognitionEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    count_statement = select(func.count(RecognitionEvent.id)).where(*filters)

    try:
        items = list(db.scalars(statement).all())
        total = int(db.scalar(count_statement) or 0)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter l'historique des reconnaissances."
        ) from exc

    return RecognitionEventList(
        items=[_event_read(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


def refresh_recognition_index(db: Session) -> RecognitionIndexStatus:
    index = get_face_embedding_index()
    snapshot = index.refresh(db)
    return RecognitionIndexStatus(
        loaded=True,
        embeddings_count=len(snapshot.items),
        persons_count=snapshot.persons_count,
        refreshed_at=snapshot.refreshed_at,
        expires_in_seconds=index.expires_in_seconds(),
        model_version=face_settings.model_version,
    )


def get_recognition_index_status() -> RecognitionIndexStatus:
    index = get_face_embedding_index()
    snapshot = index.status()

    if snapshot is None:
        return RecognitionIndexStatus(
            loaded=False,
            model_version=face_settings.model_version,
        )

    return RecognitionIndexStatus(
        loaded=True,
        embeddings_count=len(snapshot.items),
        persons_count=snapshot.persons_count,
        refreshed_at=snapshot.refreshed_at,
        expires_in_seconds=index.expires_in_seconds(),
        model_version=face_settings.model_version,
    )
