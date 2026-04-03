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
    session_manager.tabid_to_sid.clear()
    yield
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sid.clear()


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
    mock_session = Session(tab_id, 999, 12345, user_id)
    session_manager.add_session(mock_session)

    response = client.get("/api/management/sessions")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) >= 1
    assert any(s["tab_id"] == tab_id for s in data)

    # Cleanup
    session_manager.remove_session(tab_id)


def test_terminate_managed_session(client):
    # Add a mock session
    tab_id = "terminate-tab-id"
    pid = 99999
    user_id = "admin"
    mock_session = Session(tab_id, 888, pid, user_id)
    session_manager.add_session(mock_session)

    with patch("os.kill") as mock_kill, patch("os.waitpid") as mock_waitpid:
        response = client.delete(f"/api/management/sessions/{tab_id}")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"

        mock_kill.assert_called_once_with(pid, signal.SIGKILL)

        # Verify session is removed
        assert session_manager.get_session(tab_id) is None


def test_terminate_managed_session_not_found(client):
    response = client.delete("/api/management/sessions/non-existent")
    assert response.status_code == 404
    data = json.loads(response.data)
    assert "error" in data


def test_resume_new_local():
    from src.process_manager import build_terminal_command
    from unittest.mock import patch

    with patch("src.process_manager.fetch_sessions_for_host") as mock_fetch:
        mock_fetch.return_value = {
            "output": "  1. Session A (date)\n  3. Session B (date)\n",
            "error": None,
        }
        cmd = build_terminal_command(None, None, "new", "/tmp/ssh")
        cmd_str = " ".join(cmd)
        assert "gemini -r" not in cmd_str


def test_resume_new_ssh():
    from src.process_manager import build_terminal_command
    from unittest.mock import patch

    with patch("src.process_manager.fetch_sessions_for_host") as mock_fetch:
        mock_fetch.return_value = {"output": "  5. Session (date)\n", "error": None}
        cmd = build_terminal_command("user@host", "~", "new", "/tmp/ssh")
        cmd_str = " ".join(cmd)
        assert "gemini -r" not in cmd_str


def test_resume_new_no_sessions():
    from src.process_manager import build_terminal_command
    from unittest.mock import patch

    with patch("src.process_manager.fetch_sessions_for_host") as mock_fetch:
        mock_fetch.return_value = {"output": "", "error": None}
        cmd = build_terminal_command("user@host", "~", "new", "/tmp/ssh")
        cmd_str = " ".join(cmd)
        assert "gemini -r" not in cmd_str


def test_terminate_all_managed_sessions(client):
    # Add a couple of mock sessions for admin
    session1 = Session("tab-1", 101, 1001, "admin")
    session2 = Session("tab-2", 102, 1002, "admin")
    # Add a mock session for another user
    session3 = Session("tab-3", 103, 1003, "other_user")

    session_manager.add_session(session1)
    session_manager.add_session(session2)
    session_manager.add_session(session3)

    with patch("os.kill") as mock_kill, patch("os.close") as mock_close:
        response = client.post("/api/sessions/terminate_all")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert data["count"] == 2

        assert mock_kill.call_count == 2
        # waitpid removed, handled by background task
        assert mock_close.call_count == 2

        # Verify only the current user's sessions are removed
        assert session_manager.get_session("tab-1") is None
        assert session_manager.get_session("tab-2") is None
        assert session_manager.get_session("tab-3", "other_user") is not None
