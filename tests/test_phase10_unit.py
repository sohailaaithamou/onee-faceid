from types import SimpleNamespace

from app.core.security import hash_password, verify_password
from app.schemas.presence import PresenceEventType
from app.services.presence_service import _next_event_type
from app.vision.settings import face_settings


def test_first_presence_is_entry() -> None:
    assert _next_event_type(None) == PresenceEventType.ENTRY


def test_entry_is_followed_by_exit() -> None:
    last_event = SimpleNamespace(event_type="ENTRY")
    assert _next_event_type(last_event) == PresenceEventType.EXIT


def test_exit_is_followed_by_entry() -> None:
    last_event = SimpleNamespace(event_type="EXIT")
    assert _next_event_type(last_event) == PresenceEventType.ENTRY


def test_password_is_hashed_and_verified() -> None:
    password = "MotDePasse-Test-2026!"
    encoded = hash_password(password)

    assert encoded != password
    assert verify_password(password, encoded)
    assert not verify_password("MauvaisMotDePasse", encoded)


def test_face_thresholds_are_valid() -> None:
    assert 0.0 <= face_settings.detection_threshold <= 1.0
    assert -1.0 <= face_settings.enrollment_min_similarity <= 1.0
    assert -1.0 <= face_settings.recognition_threshold <= 1.0
