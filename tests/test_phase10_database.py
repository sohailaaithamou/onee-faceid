import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.system_service import get_system_readiness


pytestmark = pytest.mark.integration


def test_database_connection_and_schema() -> None:
    with SessionLocal() as db:
        result = db.execute(
            text(
                """
                SELECT
                    current_database() AS database_name,
                    current_schema() AS schema_name
                """
            )
        ).mappings().one()

    assert result["database_name"] == "faceid_onee"
    assert result["schema_name"] in {"faceid", "public"}


def test_final_database_readiness_has_no_failures() -> None:
    with SessionLocal() as db:
        report = get_system_readiness(db)

    failed = [check for check in report.checks if check.state.value == "FAIL"]
    assert failed == [], " | ".join(
        f"{check.label}: {check.detail}" for check in failed
    )


def test_current_presence_view_is_readable() -> None:
    with SessionLocal() as db:
        count = db.scalar(
            text("SELECT COUNT(*) FROM faceid.v_current_presence")
        )

    assert int(count or 0) >= 0
