from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_is_available() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_login_page_is_available() -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_dashboard_page_is_available() -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200


def test_protected_dashboard_requires_authentication() -> None:
    response = client.get("/dashboard/overview")
    assert response.status_code == 401


def test_system_readiness_requires_authentication() -> None:
    response = client.get("/system/readiness")
    assert response.status_code == 401


def test_all_main_routes_are_exposed() -> None:
    expected = {
        "/organizations",
        "/organizational-units",
        "/employees",
        "/visitors",
        "/visits",
        "/face-enrollments/{person_id}",
        "/recognitions",
        "/presence/current",
        "/dashboard/overview",
        "/auth/login",
        "/user-accounts",
        "/system/readiness",
    }
    actual = set(app.openapi().get("paths", {}).keys())
    assert expected <= actual
