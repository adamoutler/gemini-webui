import pytest
import os
import json
import signal
from unittest.mock import patch
from src.app import app, init_app, session_manager, Session


@pytest.fixture(autouse=True)
def setup_teardown():
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sids.clear()
    yield
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sids.clear()


@pytest.fixture
def client(test_data_dir, monkeypatch):
    app.config["TESTING"] = True
    app.config["DATA_DIR"] = str(test_data_dir)
    app.config["BYPASS_AUTH_FOR_TESTING"] = "true"
    monkeypatch.setenv("BYPASS_AUTH_FOR_TESTING", "true")
    app.config["WTF_CSRF_ENABLED"] = False

    # Force initialization to set up globals and paths
    with app.app_context():
        init_app()
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["user_id"] = "admin"
        yield client


def test_list_management_sessions(client):
    # Add a mock session
    tab_id = "test-tab-id"
    user_id = "admin"
    mock_session = Session(tab_id, None, 12345, user_id)
    session_manager.add_session(mock_session)

    response = client.get("/api/management/sessions")
    assert response.status_code == 200
    data = __import__("json").loads(response.data)
    assert len(data) >= 1
    assert any(s["tab_id"] == tab_id for s in data)

    # Cleanup
    session_manager.remove_session(tab_id)


def test_terminate_managed_session_not_found(client):
    response = client.delete("/api/management/sessions/non-existent")
    assert response.status_code == 404


def test_resume_new_local():
    from src.services.process_engine import build_terminal_command
    from unittest.mock import patch

    with patch("src.services.process_engine.fetch_sessions_for_host") as mock_fetch:
        mock_fetch.return_value = {
            "output": "  1. Session A (date)\n  3. Session B (date)\n",
            "error": None,
        }
        cmd = build_terminal_command(None, None, "new", "/tmp/ssh")
        cmd_str = " ".join(cmd)
        assert "gemini -r" not in cmd_str
