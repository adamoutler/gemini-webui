import pytest
import json
from unittest.mock import patch, PropertyMock
from src.app import app, env_config, register_blueprints


@pytest.fixture(autouse=True)
def init_test_app():
    # Only register if not already registered to avoid errors in pytest runner
    if not hasattr(app, "blueprints_registered"):
        register_blueprints(app)
        app.blueprints_registered = True

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.secret_key = "test_secret_key"
    with app.test_client() as client:
        yield client


def test_create_share_unauthenticated(client):
    with patch.object(
        type(env_config),
        "BYPASS_AUTH_FOR_TESTING",
        new_callable=PropertyMock,
        return_value=False,
    ):
        response = client.post(
            "/api/shares/create",
            json={"session_name": "test_session", "html_content": "<p>test</p>"},
        )
        assert response.status_code == 401


def test_list_shares_unauthenticated(client):
    with patch.object(
        type(env_config),
        "BYPASS_AUTH_FOR_TESTING",
        new_callable=PropertyMock,
        return_value=False,
    ):
        response = client.get("/api/shares")
        assert response.status_code == 401


def test_delete_share_unauthenticated(client):
    with patch.object(
        type(env_config),
        "BYPASS_AUTH_FOR_TESTING",
        new_callable=PropertyMock,
        return_value=False,
    ):
        response = client.delete("/api/shares/1234")
        assert response.status_code == 401


def test_share_lifecycle(client):
    # Authenticate for testing
    with patch.object(
        type(env_config),
        "BYPASS_AUTH_FOR_TESTING",
        new_callable=PropertyMock,
        return_value=True,
    ):
        # Create share
        create_resp = client.post(
            "/api/shares/create",
            json={
                "session_name": "My Test Session",
                "html_content": "<span class='test'>Hello Terminal</span>",
            },
        )
        assert create_resp.status_code == 200
        data = json.loads(create_resp.data)
        share_id = data.get("share_id")
        assert share_id is not None

        # List shares
        list_resp = client.get("/api/shares")
        assert list_resp.status_code == 200
        shares = json.loads(list_resp.data)
        assert any(s["id"] == share_id for s in shares)

        # View share (unprotected route)
        view_resp = client.get(f"/s/{share_id}")
        assert view_resp.status_code == 200
        html = view_resp.data.decode("utf-8")
        assert "<span class='test'>Hello Terminal</span>" in html
        assert "My Test Session" in html
        assert "terminal-wrapper" in html

        # Delete share
        del_resp = client.delete(f"/api/shares/{share_id}")
        assert del_resp.status_code == 200

        # Verify deletion
        view_resp_after = client.get(f"/s/{share_id}")
        assert view_resp_after.status_code == 404


def test_path_traversal(client):
    # Try with an invalid character to trigger the 400
    response = client.get("/s/invalid_id_!@#$")
    assert response.status_code == 400
    assert b"Invalid share ID" in response.data

    # Try directory traversal string directly to bypass router slash blocking if any
    response2 = client.get("/s/..%2F..%2Fetc%2Fpasswd")
    # If the router blocks it before our view function, it will be 404
    # If it gets to our view function, it will be 400 due to regex
    assert response2.status_code in [400, 404]
