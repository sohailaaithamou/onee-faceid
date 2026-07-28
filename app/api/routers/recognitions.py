from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.recognition import (
    RecognitionAttemptResult,
    RecognitionDecision,
    RecognitionEventList,
    RecognitionEventRead,
    RecognitionIndexStatus,
)
from app.services.recognition_service import (
    RecognitionUpload,
    get_recognition_event,
    get_recognition_index_status,
    list_recognition_events,
    recognize_face,
    refresh_recognition_index,
)

router = APIRouter(tags=["Face recognition"])
SessionDependency = Annotated[Session, Depends(get_db)]


def _read_upload(upload: UploadFile) -> bytes:
    upload.file.seek(0)
    return upload.file.read()


@router.post(
    "/recognitions",
    response_model=RecognitionAttemptResult,
    status_code=status.HTTP_201_CREATED,
)
def recognize_face_route(
    db: SessionDependency,
    image: Annotated[
        UploadFile,
        File(description="Image contenant exactement un visage à identifier."),
    ],
    device_code: Annotated[
        str | None,
        Form(description="Code de la caméra ou du poste, par exemple RECEPTION-01."),
    ] = None,
    refresh_index: Annotated[
        bool,
        Form(description="Recharge les embeddings depuis PostgreSQL avant la comparaison."),
    ] = False,
) -> RecognitionAttemptResult:
    upload = RecognitionUpload(
        filename=image.filename or "recognition_image",
        content_type=image.content_type,
        content=_read_upload(image),
    )
    return recognize_face(
        db,
        upload,
        device_code=device_code,
        refresh_index=refresh_index,
    )


@router.post(
    "/recognition-index/refresh",
    response_model=RecognitionIndexStatus,
)
def refresh_recognition_index_route(
    db: SessionDependency,
) -> RecognitionIndexStatus:
    return refresh_recognition_index(db)


@router.get(
    "/recognition-index/status",
    response_model=RecognitionIndexStatus,
)
def recognition_index_status_route() -> RecognitionIndexStatus:
    return get_recognition_index_status()


@router.get(
    "/recognitions",
    response_model=RecognitionEventList,
)
def list_recognition_events_route(
    db: SessionDependency,
    decision: RecognitionDecision | None = Query(default=None),
    matched_person_id: int | None = Query(default=None, ge=1),
    captured_from: datetime | None = Query(default=None),
    captured_to: datetime | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> RecognitionEventList:
    return list_recognition_events(
        db,
        decision=decision,
        matched_person_id=matched_person_id,
        captured_from=captured_from,
        captured_to=captured_to,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/recognitions/{recognition_id}",
    response_model=RecognitionEventRead,
)
def get_recognition_event_route(
    recognition_id: int,
    db: SessionDependency,
) -> RecognitionEventRead:
    return get_recognition_event(db, recognition_id)
