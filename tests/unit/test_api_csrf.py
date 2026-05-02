import pytest
from src.app import create_app
from src.routes.api import api_bp


@pytest.fixture
def client():
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "BYPASS_AUTH_FOR_TESTING": "true",
            "SECRET_KEY": "test-secret",
        }
    )

    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.mark.timeout(60)
def test_csrf_token_endpoint(client):
    response = client.get("/api/csrf-token")
    assert response.status_code == 200
    data = response.get_json()
    assert "csrf_token" in data

    # Check that caching is strictly disabled
    headers = response.headers
    assert "no-cache" in headers.get("Cache-Control", "")
    assert "no-store" in headers.get("Cache-Control", "")
    assert headers.get("Pragma") == "no-cache"
