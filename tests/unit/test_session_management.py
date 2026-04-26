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


@pytest.mark.timeout(60)
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


@pytest.mark.timeout(60)
def test_terminate_managed_session_not_found(client):
    response = client.delete("/api/management/sessions/non-existent")
    assert response.status_code == 404


@pytest.mark.timeout(60)
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


@pytest.mark.timeout(60)
def test_buffer_chunking_ansi_preservation():
    """Verify that buffer chunking does not split ANSI sequences and strips clear commands."""
    from src.gateways.terminal_socket import pty_restart
    from unittest.mock import MagicMock
    import src.gateways.terminal_socket as ts

    # Create 100KB of output with ANSI sequences
    ansi_line = "\x1b[31mThis is a red line of text.\x1b[0m\n"
    num_lines = (100 * 1024) // len(ansi_line)

    full_buffer = (ansi_line * num_lines) + "\x1b[3J" + "\x1b[2J"

    mock_session = MagicMock()
    mock_session.buffer = [full_buffer]
    mock_session.fd = 1

    emits = []

    def mock_emit(event, data, room=None):
        if event == "pty-output":
            emits.append(data["output"])

    # Mocking socketio
    old_emit = ts.socketio.emit
    old_sleep = ts.socketio.sleep
    ts.socketio.emit = mock_emit
    ts.socketio.sleep = MagicMock()

    try:
        with app.test_request_context():
            with patch("flask.request") as mock_req, patch(
                "src.gateways.terminal_socket.session_manager.reclaim_session",
                return_value=mock_session,
            ), patch("src.gateways.terminal_socket.set_winsize"), patch(
                "src.gateways.terminal_socket.session", {"user_id": "admin"}
            ), patch("src.gateways.terminal_socket.join_room"):
                mock_req.sid = "test_sid"
                pty_restart({"tab_id": "test_tab", "reclaim": True, "mode": "local"})

        assert len(emits) > 1, "Should have chunked the output"

        for chunk in emits:
            assert "\x1b[3J" not in chunk
            assert "\x1b[2J" not in chunk

        reconstructed = "".join(emits)
        assert (
            "\x1b[31mThis is a red line of text.\x1b[0m\n" * num_lines == reconstructed
        )
    finally:
        ts.socketio.emit = old_emit
        ts.socketio.sleep = old_sleep
