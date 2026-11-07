import pytest

pytest.importorskip("dash")

from app.main import dash_app  # noqa: E402


def test_health_endpoint():
    client = dash_app.server.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"


def test_version_endpoint_shape():
    client = dash_app.server.test_client()
    response = client.get("/version")
    assert response.status_code == 200
    body = response.get_json()
    assert "version" in body
    assert "commit" in body


def test_ready_endpoint_is_defined():
    client = dash_app.server.test_client()
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    body = response.get_json()
    assert body["status"] in ("ready", "not_ready")
