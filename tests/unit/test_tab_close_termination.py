import pytest
import os
import signal
from unittest.mock import patch, MagicMock
from src.services.session_store import SessionManager
from src.models.session import Session
from src.gateways.terminal_socket import on_terminate_session
from src.routes.terminal import terminate_session
from src.app import app, init_app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["BYPASS_AUTH_FOR_TESTING"] = "true"
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        init_app()
    with app.test_client() as client:
        yield client


@patch("src.models.session.fcntl.fcntl")
@patch("src.routes.terminal.kill_and_reap")
@patch("src.routes.terminal.os.close")
def test_rest_api_terminate_session(mock_os_close, mock_kill_reap, mock_fcntl, client):
    # Authenticate
    with client.session_transaction() as sess:
        sess["user_id"] = "test_user"
        sess["authenticated"] = True

    from src.services.session_store import session_manager

    test_session = Session("test_tab_123", 9999, 8888, user_id="test_user")
    session_manager.add_session(test_session)

    # Call the REST endpoint
    response = client.delete("/api/management/sessions/test_tab_123")

    assert response.status_code == 200
    assert "terminated successfully" in response.json["message"]

    # Verify process termination and fd closure
    mock_kill_reap.assert_called_once_with(8888)
    mock_os_close.assert_called_once_with(9999)

    # Verify session is removed
    assert session_manager.get_session("test_tab_123", "test_user") is None


@patch("src.models.session.fcntl.fcntl")
@patch("src.gateways.terminal_socket.kill_and_reap")
@patch("src.gateways.terminal_socket.os.close")
@patch("src.gateways.terminal_socket.socketio.emit")
def test_socket_terminate_session(
    mock_emit, mock_os_close, mock_kill_reap, mock_fcntl, client
):
    from src.services.session_store import session_manager

    test_session = Session("test_tab_socket", 7777, 6666, user_id="test_user")
    session_manager.add_session(test_session)

    with app.test_request_context():
        # Need session variable in request context
        from flask import session

        session["user_id"] = "test_user"
        session["authenticated"] = True

        with patch("flask.request") as mock_req:
            mock_req.sid = "test_sid_123"
            on_terminate_session({"tab_id": "test_tab_socket"})

    mock_kill_reap.assert_called_once_with(6666)
    mock_os_close.assert_called_once_with(7777)

    assert session_manager.get_session("test_tab_socket", "test_user") is None
    mock_emit.assert_any_call(
        "session-terminated", {"tab_id": "test_tab_socket"}, room="test_tab_socket"
    )
