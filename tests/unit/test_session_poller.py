import time
from unittest.mock import MagicMock
from src.services.session_poller import SessionPollerManager


def test_session_poller_active_interval(monkeypatch):
    # Ensure fresh singleton instance for test
    SessionPollerManager._instance = None
    manager = SessionPollerManager()
    manager.last_frontend_request_time = time.time()
    manager.is_running = True

    mock_fetch = MagicMock()
    mock_sleep = MagicMock()

    def side_effect(*args, **kwargs):
        manager.is_running = False  # Break loop

    mock_fetch.side_effect = side_effect

    monkeypatch.setattr(
        "src.services.session_poller.fetch_sessions_for_host", mock_fetch
    )
    monkeypatch.setattr("src.services.session_poller.eventlet.sleep", mock_sleep)

    manager._poll_host({"label": "test", "target": "test"})

    mock_fetch.assert_called_once()
    mock_sleep.assert_called_once_with(5)


def test_session_poller_backoff_interval(monkeypatch):
    # Ensure fresh singleton instance for test
    SessionPollerManager._instance = None
    manager = SessionPollerManager()
    # Simulate last request was 130 seconds ago
    manager.last_frontend_request_time = time.time() - 130
    manager.is_running = True

    mock_fetch = MagicMock()
    mock_sleep = MagicMock()

    def side_effect(*args, **kwargs):
        manager.is_running = False  # Break loop

    mock_fetch.side_effect = side_effect

    monkeypatch.setattr(
        "src.services.session_poller.fetch_sessions_for_host", mock_fetch
    )
    monkeypatch.setattr("src.services.session_poller.eventlet.sleep", mock_sleep)

    manager._poll_host({"label": "test", "target": "test"})

    mock_fetch.assert_called_once()
    mock_sleep.assert_called_once_with(120)
