from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.presence import (
    CurrentPresenceList,
    PersonPresenceState,
    PresenceEventList,
    PresenceEventRead,
    PresenceEventType,
    PresenceFromRecognitionCreate,
    PresenceRegistrationResult,
    PresenceSource,
    PresenceStatus,
)
from app.services.presence_service import (
    create_presence_from_recognition,
    get_current_presence,
    get_person_presence_state,
    get_presence_event,
    list_presence_events,
)

router = APIRouter(tags=["Attendance and presence"])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.post(
    "/presence-events/from-recognition/{recognition_id}",
    response_model=PresenceRegistrationResult,
    status_code=status.HTTP_201_CREATED,
)
def create_presence_from_recognition_route(
    recognition_id: int,
    payload: PresenceFromRecognitionCreate,
    db: SessionDependency,
) -> PresenceRegistrationResult:
    return create_presence_from_recognition(
        db,
        recognition_id,
        payload,
    )


@router.get(
    "/presence/current",
    response_model=CurrentPresenceList,
)
def current_presence_route(
    db: SessionDependency,
) -> CurrentPresenceList:
    return get_current_presence(db)


@router.get(
    "/persons/{person_id}/presence-state",
    response_model=PersonPresenceState,
)
def person_presence_state_route(
    person_id: int,
    db: SessionDependency,
) -> PersonPresenceState:
    return get_person_presence_state(db, person_id)


@router.get(
    "/presence-events",
    response_model=PresenceEventList,
)
def list_presence_events_route(
    db: SessionDependency,
    person_id: int | None = Query(default=None, ge=1),
    event_type: PresenceEventType | None = Query(default=None),
    source: PresenceSource | None = Query(default=None),
    status_filter: PresenceStatus | None = Query(default=None, alias="status"),
    event_from: datetime | None = Query(default=None),
    event_to: datetime | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PresenceEventList:
    return list_presence_events(
        db,
        person_id=person_id,
        event_type=event_type,
        source=source,
        status=status_filter,
        event_from=event_from,
        event_to=event_to,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/presence-events/{presence_id}",
    response_model=PresenceEventRead,
)
def get_presence_event_route(
    presence_id: int,
    db: SessionDependency,
) -> PresenceEventRead:
    return get_presence_event(db, presence_id)
