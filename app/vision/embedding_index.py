from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import RLock
from time import monotonic

import numpy as np
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.models import EmployeeProfile, FaceEmbedding, Person, VisitorProfile
from app.vision.settings import face_settings


@dataclass(frozen=True, slots=True)
class IndexedFaceEmbedding:
    embedding_id: int
    person_id: int
    first_name: str
    last_name: str
    person_type: str
    capture_label: str | None
    vector: np.ndarray


@dataclass(frozen=True, slots=True)
class EmbeddingIndexSnapshot:
    items: tuple[IndexedFaceEmbedding, ...]
    persons_count: int
    refreshed_at: datetime


class FaceEmbeddingIndex:
    """Cache mémoire des embeddings actifs utilisés pour l'identification."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshot: EmbeddingIndexSnapshot | None = None
        self._loaded_at_monotonic: float | None = None

    def get(
        self,
        db: Session,
        *,
        force_refresh: bool = False,
    ) -> EmbeddingIndexSnapshot:
        with self._lock:
            expired = self._is_expired()
            if force_refresh or self._snapshot is None or expired:
                self._snapshot = self._load(db)
                self._loaded_at_monotonic = monotonic()
            return self._snapshot

    def refresh(self, db: Session) -> EmbeddingIndexSnapshot:
        return self.get(db, force_refresh=True)

    def status(self) -> EmbeddingIndexSnapshot | None:
        with self._lock:
            return self._snapshot

    def expires_in_seconds(self) -> int | None:
        with self._lock:
            if self._loaded_at_monotonic is None:
                return None

            elapsed = monotonic() - self._loaded_at_monotonic
            remaining = face_settings.recognition_cache_seconds - elapsed
            return max(0, int(round(remaining)))

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None
            self._loaded_at_monotonic = None

    def _is_expired(self) -> bool:
        if self._loaded_at_monotonic is None:
            return True
        return (
            monotonic() - self._loaded_at_monotonic
            >= face_settings.recognition_cache_seconds
        )

    @staticmethod
    def _normalize(vector_values: list[float]) -> np.ndarray | None:
        vector = np.asarray(vector_values, dtype=np.float32).reshape(-1)
        if vector.size != 128 or not np.all(np.isfinite(vector)):
            return None

        norm = float(np.linalg.norm(vector))
        if norm <= 1e-12:
            return None

        normalized = vector / norm
        normalized.setflags(write=False)
        return normalized

    @staticmethod
    def _is_person_eligible(
        person: Person,
        employee_profiles: dict[int, EmployeeProfile],
        visitor_profiles: dict[int, VisitorProfile],
        today: date,
    ) -> bool:
        if not person.active:
            return False

        if person.person_type == "EMPLOYEE":
            profile = employee_profiles.get(person.id)
            if profile is None or profile.employment_status != "ACTIVE":
                return False
            if profile.end_date is not None and profile.end_date < today:
                return False
            return True

        if person.person_type == "VISITOR":
            profile = visitor_profiles.get(person.id)
            if profile is None or not profile.active:
                return False
            if profile.valid_from is not None and today < profile.valid_from:
                return False
            if profile.valid_until is not None and today > profile.valid_until:
                return False
            return True

        return False

    def _load(self, db: Session) -> EmbeddingIndexSnapshot:
        statement = (
            select(FaceEmbedding, Person)
            .join(Person, Person.id == FaceEmbedding.person_id)
            .where(
                FaceEmbedding.is_active.is_(True),
                FaceEmbedding.model_name == "SFace",
                FaceEmbedding.model_version == face_settings.model_version,
                Person.active.is_(True),
            )
            .order_by(FaceEmbedding.person_id, FaceEmbedding.id)
        )

        try:
            rows = list(db.execute(statement).all())

            employee_ids = {
                person.id
                for _, person in rows
                if person.person_type == "EMPLOYEE"
            }
            visitor_ids = {
                person.id
                for _, person in rows
                if person.person_type == "VISITOR"
            }

            employee_profiles: dict[int, EmployeeProfile] = {}
            if employee_ids:
                profiles = db.scalars(
                    select(EmployeeProfile).where(
                        EmployeeProfile.person_id.in_(employee_ids)
                    )
                ).all()
                employee_profiles = {
                    profile.person_id: profile for profile in profiles
                }

            visitor_profiles: dict[int, VisitorProfile] = {}
            if visitor_ids:
                profiles = db.scalars(
                    select(VisitorProfile).where(
                        VisitorProfile.person_id.in_(visitor_ids)
                    )
                ).all()
                visitor_profiles = {
                    profile.person_id: profile for profile in profiles
                }

        except SQLAlchemyError as exc:
            raise DatabaseOperationError(
                "Impossible de charger l'index des embeddings faciaux."
            ) from exc

        today = date.today()
        items: list[IndexedFaceEmbedding] = []
        person_ids: set[int] = set()

        for embedding, person in rows:
            if not self._is_person_eligible(
                person,
                employee_profiles,
                visitor_profiles,
                today,
            ):
                continue

            normalized = self._normalize(embedding.embedding)
            if normalized is None:
                continue

            items.append(
                IndexedFaceEmbedding(
                    embedding_id=embedding.id,
                    person_id=person.id,
                    first_name=person.first_name,
                    last_name=person.last_name,
                    person_type=person.person_type,
                    capture_label=embedding.capture_label,
                    vector=normalized,
                )
            )
            person_ids.add(person.id)

        return EmbeddingIndexSnapshot(
            items=tuple(items),
            persons_count=len(person_ids),
            refreshed_at=datetime.now(timezone.utc),
        )


face_embedding_index = FaceEmbeddingIndex()


def get_face_embedding_index() -> FaceEmbeddingIndex:
    return face_embedding_index
