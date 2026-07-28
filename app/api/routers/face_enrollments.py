from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.face_enrollment import (
    FaceEmbeddingRead,
    FaceEmbeddingStatusUpdate,
    FaceEnrollmentResult,
    PersonFaceEmbeddingsRead,
)
from app.services.face_enrollment_service import (
    EnrollmentUpload,
    enroll_person_faces,
    list_person_face_embeddings,
    update_face_embedding_status,
)

router = APIRouter(tags=["Face enrollment"])
SessionDependency = Annotated[Session, Depends(get_db)]


def _read_upload(upload: UploadFile) -> bytes:
    upload.file.seek(0)
    return upload.file.read()


@router.post(
    "/face-enrollments/{person_id}",
    response_model=FaceEnrollmentResult,
    status_code=status.HTTP_201_CREATED,
)
def enroll_person_faces_route(
    person_id: int,
    db: SessionDependency,
    front_image: Annotated[
        UploadFile,
        File(description="Photo de face, une seule personne."),
    ],
    left_image: Annotated[
        UploadFile,
        File(description="Visage légèrement tourné vers la gauche."),
    ],
    right_image: Annotated[
        UploadFile,
        File(description="Visage légèrement tourné vers la droite."),
    ],
    replace_existing: Annotated[
        bool,
        Form(description="Désactive les anciens embeddings avant d'enregistrer les nouveaux."),
    ] = False,
) -> FaceEnrollmentResult:
    uploads = [
        EnrollmentUpload(
            label="FRONT",
            filename=front_image.filename or "front_image",
            content_type=front_image.content_type,
            content=_read_upload(front_image),
        ),
        EnrollmentUpload(
            label="LEFT",
            filename=left_image.filename or "left_image",
            content_type=left_image.content_type,
            content=_read_upload(left_image),
        ),
        EnrollmentUpload(
            label="RIGHT",
            filename=right_image.filename or "right_image",
            content_type=right_image.content_type,
            content=_read_upload(right_image),
        ),
    ]

    return enroll_person_faces(
        db,
        person_id,
        uploads,
        replace_existing=replace_existing,
    )


@router.get(
    "/face-enrollments/{person_id}",
    response_model=PersonFaceEmbeddingsRead,
)
def list_person_face_embeddings_route(
    person_id: int,
    db: SessionDependency,
    active_only: bool = Query(default=True),
) -> PersonFaceEmbeddingsRead:
    return list_person_face_embeddings(
        db,
        person_id,
        active_only=active_only,
    )


@router.put(
    "/face-embeddings/{embedding_id}/status",
    response_model=FaceEmbeddingRead,
)
def update_face_embedding_status_route(
    embedding_id: int,
    payload: FaceEmbeddingStatusUpdate,
    db: SessionDependency,
) -> FaceEmbeddingRead:
    return update_face_embedding_status(db, embedding_id, payload)
