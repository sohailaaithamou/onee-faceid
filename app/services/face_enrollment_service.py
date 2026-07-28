from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
)
from app.models import EmployeeProfile, FaceEmbedding, Person, VisitorProfile
from app.schemas.face_enrollment import (
    FaceCaptureDiagnostic,
    FaceEmbeddingRead,
    FaceEmbeddingStatusUpdate,
    FaceEnrollmentPersonSummary,
    FaceEnrollmentResult,
    FaceSimilaritySummary,
    PersonFaceEmbeddingsRead,
)
from app.vision import FaceEngine, FaceProcessingError, get_face_engine
from app.vision.settings import face_settings


@dataclass(frozen=True, slots=True)
class EnrollmentUpload:
    label: str
    filename: str
    content_type: str | None
    content: bytes


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint = _constraint_name(exc)

        if constraint == "fk_face_embedding_person":
            raise NotFoundError("La personne associée à l'embedding est introuvable.") from exc

        if constraint == "chk_face_embedding_dimension":
            raise BusinessRuleError(
                "L'embedding facial doit contenir exactement 128 valeurs valides."
            ) from exc

        if constraint == "chk_face_embedding_quality":
            raise BusinessRuleError(
                "Le score de qualité facial doit être compris entre 0 et 1."
            ) from exc

        raise ConflictError(
            "L'enrôlement facial ne peut pas être enregistré à cause d'une contrainte de données."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enrôlement facial."
    ) from exc


def _person_summary(person: Person) -> FaceEnrollmentPersonSummary:
    return FaceEnrollmentPersonSummary(
        id=person.id,
        first_name=person.first_name,
        last_name=person.last_name,
        person_type=person.person_type,
        active=person.active,
    )


def _embedding_read(embedding: FaceEmbedding) -> FaceEmbeddingRead:
    return FaceEmbeddingRead(
        id=embedding.id,
        person_id=embedding.person_id,
        model_name=embedding.model_name,
        model_version=embedding.model_version,
        capture_label=embedding.capture_label,
        quality_score=(
            float(embedding.quality_score)
            if embedding.quality_score is not None
            else None
        ),
        is_active=embedding.is_active,
        created_at=embedding.created_at,
    )


def _get_enrollable_person(db: Session, person_id: int) -> Person:
    try:
        person = db.get(Person, person_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter la personne.") from exc

    if person is None:
        raise NotFoundError("Personne introuvable.")

    if not person.active:
        raise BusinessRuleError(
            "La personne est désactivée et ne peut pas être enrôlée."
        )

    if person.person_type == "EMPLOYEE":
        try:
            profile = db.get(EmployeeProfile, person_id)
        except SQLAlchemyError as exc:
            raise DatabaseOperationError(
                "Impossible de consulter le profil de l'agent."
            ) from exc

        if profile is None:
            raise BusinessRuleError("Le profil agent de cette personne est incomplet.")
        if profile.employment_status != "ACTIVE":
            raise BusinessRuleError(
                "Seul un agent au statut ACTIVE peut être enrôlé."
            )

    elif person.person_type == "VISITOR":
        try:
            profile = db.get(VisitorProfile, person_id)
        except SQLAlchemyError as exc:
            raise DatabaseOperationError(
                "Impossible de consulter le profil du visiteur."
            ) from exc

        if profile is None:
            raise BusinessRuleError("Le profil visiteur de cette personne est incomplet.")
        if not profile.active:
            raise BusinessRuleError(
                "Le profil visiteur est désactivé et ne peut pas être enrôlé."
            )
    else:
        raise BusinessRuleError("Le type de personne ne permet pas l'enrôlement facial.")

    return person


def _validate_upload(upload: EnrollmentUpload) -> None:
    allowed_content_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }

    if upload.content_type and upload.content_type.lower() not in allowed_content_types:
        raise BusinessRuleError(
            f"{upload.label} : format non accepté. Utilisez JPEG, PNG ou WebP."
        )

    if not upload.content:
        raise BusinessRuleError(f"{upload.label} : le fichier est vide.")

    if len(upload.content) > face_settings.max_upload_bytes:
        maximum_mb = face_settings.max_upload_bytes / (1024 * 1024)
        raise BusinessRuleError(
            f"{upload.label} : le fichier dépasse la limite de {maximum_mb:.0f} Mo."
        )


def _active_embedding_count(db: Session, person_id: int) -> int:
    statement = select(FaceEmbedding.id).where(
        FaceEmbedding.person_id == person_id,
        FaceEmbedding.is_active.is_(True),
    )
    try:
        return len(db.scalars(statement).all())
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter les embeddings faciaux existants."
        ) from exc


def enroll_person_faces(
    db: Session,
    person_id: int,
    uploads: list[EnrollmentUpload],
    *,
    replace_existing: bool = False,
    engine: FaceEngine | None = None,
) -> FaceEnrollmentResult:
    if len(uploads) != 3:
        raise BusinessRuleError(
            "L'enrôlement nécessite exactement trois captures : FRONT, LEFT et RIGHT."
        )

    expected_labels = {"FRONT", "LEFT", "RIGHT"}
    actual_labels = {upload.label for upload in uploads}
    if actual_labels != expected_labels:
        raise BusinessRuleError(
            "Les captures doivent porter les libellés FRONT, LEFT et RIGHT."
        )

    person = _get_enrollable_person(db, person_id)
    active_count = _active_embedding_count(db, person_id)
    if active_count > 0 and not replace_existing:
        raise ConflictError(
            "Cette personne possède déjà des embeddings actifs. "
            "Utilisez replace_existing=true pour refaire l'enrôlement."
        )

    for upload in uploads:
        _validate_upload(upload)

    face_engine = engine or get_face_engine()
    extracted_by_label = {}
    diagnostics: list[FaceCaptureDiagnostic] = []

    for upload in uploads:
        try:
            extracted = face_engine.extract(upload.content)
        except FaceProcessingError as exc:
            raise BusinessRuleError(f"Capture {upload.label} : {exc}") from exc
        except RuntimeError as exc:
            raise DatabaseOperationError(str(exc)) from exc

        extracted_by_label[upload.label] = extracted
        diagnostics.append(
            FaceCaptureDiagnostic(
                capture_label=upload.label,
                filename=upload.filename,
                detection_score=extracted.detection_score,
                sharpness_score=extracted.sharpness_score,
                face_width=extracted.face_width,
                face_height=extracted.face_height,
                quality_score=extracted.quality_score,
            )
        )

    front = extracted_by_label["FRONT"].embedding
    left = extracted_by_label["LEFT"].embedding
    right = extracted_by_label["RIGHT"].embedding

    similarities = {
        "front_left": face_engine.cosine_similarity(front, left),
        "front_right": face_engine.cosine_similarity(front, right),
        "left_right": face_engine.cosine_similarity(left, right),
    }
    minimum_similarity = min(similarities.values())

    if minimum_similarity < face_settings.enrollment_min_similarity:
        raise BusinessRuleError(
            "Les trois captures ne semblent pas appartenir à la même personne. "
            f"Similarité minimale={minimum_similarity:.4f}, "
            f"seuil={face_settings.enrollment_min_similarity:.4f}."
        )

    try:
        if replace_existing:
            current_statement = select(FaceEmbedding).where(
                FaceEmbedding.person_id == person_id,
                FaceEmbedding.is_active.is_(True),
            )
            for current in db.scalars(current_statement):
                current.is_active = False

        created: list[FaceEmbedding] = []
        for upload in uploads:
            extracted = extracted_by_label[upload.label]
            embedding = FaceEmbedding(
                person_id=person_id,
                embedding=extracted.embedding,
                model_name="SFace",
                model_version=face_settings.model_version,
                capture_label=upload.label,
                quality_score=Decimal(f"{extracted.quality_score:.4f}"),
                is_active=True,
            )
            db.add(embedding)
            created.append(embedding)

        db.flush()
        db.commit()

        for embedding in created:
            db.refresh(embedding)

    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
        raise AssertionError("unreachable")

    return FaceEnrollmentResult(
        message="Enrôlement facial enregistré avec trois embeddings actifs.",
        person=_person_summary(person),
        embeddings=[_embedding_read(item) for item in created],
        diagnostics=diagnostics,
        similarities=FaceSimilaritySummary(
            front_left=round(similarities["front_left"], 6),
            front_right=round(similarities["front_right"], 6),
            left_right=round(similarities["left_right"], 6),
            minimum=round(minimum_similarity, 6),
            required_minimum=face_settings.enrollment_min_similarity,
        ),
    )


def list_person_face_embeddings(
    db: Session,
    person_id: int,
    *,
    active_only: bool = True,
) -> PersonFaceEmbeddingsRead:
    try:
        person = db.get(Person, person_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter la personne.") from exc

    if person is None:
        raise NotFoundError("Personne introuvable.")

    statement = (
        select(FaceEmbedding)
        .where(FaceEmbedding.person_id == person_id)
        .order_by(FaceEmbedding.created_at.desc(), FaceEmbedding.id.desc())
    )
    if active_only:
        statement = statement.where(FaceEmbedding.is_active.is_(True))

    try:
        embeddings = list(db.scalars(statement).all())
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter les embeddings faciaux."
        ) from exc

    return PersonFaceEmbeddingsRead(
        person=_person_summary(person),
        embeddings=[_embedding_read(item) for item in embeddings],
        total=len(embeddings),
    )


def update_face_embedding_status(
    db: Session,
    embedding_id: int,
    payload: FaceEmbeddingStatusUpdate,
) -> FaceEmbeddingRead:
    try:
        embedding = db.get(FaceEmbedding, embedding_id)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Impossible de consulter l'embedding facial.") from exc

    if embedding is None:
        raise NotFoundError("Embedding facial introuvable.")

    embedding.is_active = payload.is_active

    try:
        db.commit()
        db.refresh(embedding)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
        raise AssertionError("unreachable")

    return _embedding_read(embedding)
