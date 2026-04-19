from src.gateways.terminal_socket import (
    pty_restart,
    set_winsize,
    background_session_preloader,
)
import pytest
from unittest.mock import patch
import os
import signal
from src.app import (
    cleanup_orphaned_ptys,
    session_results_cache,
)


@pytest.fixture
def mock_socketio():
    with patch("src.gateways.terminal_socket.socketio") as mock:
        yield mock


@pytest.fixture
def mock_pty():
    with patch("src.app.pty.fork") as mock_fork:
        yield mock_fork


def test_cleanup_orphaned_ptys(mock_socketio):
    # Ensure it breaks loop
    os.environ["BYPASS_AUTH_FOR_TESTING"] = "true"

    # Mock some ptys
    from src.app import session_manager, Session
    import time

    # 1. Active PTY
    active_session = Session("active", None, 123, "admin")
    session_manager.add_session(active_session)

    # 2. Orphaned PTY (old)
    old_orphan = Session("old_orphan", None, 124, "admin")
    old_orphan.orphaned_at = time.time() - 100  # 100s ago
    session_manager.add_session(old_orphan)

    # 3. Orphaned PTY (new)
    new_orphan = Session("new_orphan", None, 125, "admin")
    new_orphan.orphaned_at = time.time() - 10  # 10s ago
    session_manager.add_session(new_orphan)

    with patch("os.killpg") as mock_kill, patch("os.waitpid") as mock_wait, patch(
        "os.getpgid", side_effect=lambda x: x
    ):  # Mock ORPHANED_SESSION_TTL to 60 for testing
        from src.app import app

        app.config["ORPHANED_SESSION_TTL"] = 60

        cleanup_orphaned_ptys()

        # Only old_orphan should be killed
        assert mock_kill.call_count == 1
        # SessionManager now uses os.getpgid(pid)
        mock_kill.assert_called_with(os.getpgid(124), 9)

        # Verify it was removed from the session manager
        assert session_manager.get_session("old_orphan") is None
        # Verify active and new_orphan still exist
        assert session_manager.get_session("active") is not None
        assert session_manager.get_session("new_orphan") is not None


@patch("src.config.get_config")
def test_background_session_preloader(mock_get_config):
    mock_get_config.return_value = {"HOSTS": [{"label": "local", "type": "local"}]}

    with patch(
        "src.gateways.terminal_socket.fetch_sessions_for_host"
    ) as mock_fetch, patch(
        "src.app.socketio.sleep", side_effect=[None, Exception("Stop loop")]
    ):
        mock_fetch.return_value = {"output": "some sessions", "error": None}

        try:
            background_session_preloader()
        except Exception as e:
            assert str(e) == "Stop loop"

        assert "local:local:" in session_results_cache
        assert session_results_cache["local:local:"]["output"] == "some sessions"


def test_pty_restart_basic(mock_socketio, mock_pty):
    from src.app import app
    from unittest.mock import MagicMock

    # Use non-zero child_pid to avoid child branch execution in tests
    mock_pty.return_value = (1234, 10)

    with app.test_request_context("/"):
        mock_request = MagicMock()
        mock_request.sid = "test-sid"
        # Patch where it's USED in src.app
        with patch("src.gateways.terminal_socket.request", mock_request), patch(
            "src.config.get_config_paths"
        ) as mock_paths, patch("src.config.get_config") as mock_get_config, patch(
            "shutil.which", return_value=None
        ), patch("os.chdir"), patch("os.execv"), patch("os.closerange"), patch(
            "os.execvp"
        ) as mock_execvp, patch("os._exit"), patch(
            "src.app.build_terminal_command", return_value=["bash"]
        ) as mock_build_cmd, patch(
            "src.gateways.terminal_socket.set_winsize"
        ) as mock_set_winsize, patch("fcntl.fcntl"):
            mock_paths.return_value = ("/data", "/data/config.json", "/data/.ssh")
            mock_get_config.return_value = {
                "HOSTS": [{"target": "test@host", "env_vars": {"MY_VAR": "123"}}]
            }

            # Trigger restart (parent branch)

            pty_restart(
                {
                    "tab_id": "tab1",
                    "ssh_target": "test@host",
                    "ssh_dir": "/remote/dir",
                    "resume": True,
                }
            )

            from src.app import session_manager

            session = session_manager.get_session("tab1")
            assert session is not None
            assert session.pid == 1234


def test_pty_restart_lru_eviction(mock_socketio, mock_pty):
    from src.app import app, session_manager, Session
    import time

    # child_pid=999, fd=10
    mock_pty.return_value = (999, 10)

    # Fill up session manager with 50 sessions, each with a different last_seen
    # Use 0 active SIDs to allow eviction
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sids.clear()

    now = time.time()
    for i in range(50):
        tab_id = f"tab_{i}"
        s = Session(tab_id, None, 1000 + i, "admin")
        s.last_seen = now - (1000 - i)  # tab_0 is oldest
        session_manager.add_session(s)
        # Ensure it has 0 SIDs so it's eligible for eviction
        session_manager.tabid_to_sids[tab_id] = set()

    with app.test_request_context("/"):
        with patch("os.killpg") as mock_killpg, patch(
            "os.getpgid", side_effect=lambda x: x
        ), patch("src.gateways.terminal_socket.set_winsize"), patch("fcntl.fcntl"):
            # Attempt to start the 51st session
            # pty_restart now automatically joins room and reclaim if needed
            from unittest.mock import MagicMock

            mock_request = MagicMock()
            mock_request.sid = "sid_new"
            with patch("src.gateways.terminal_socket.request", mock_request):
                pty_restart({"tab_id": "tab_new"})

            # Verify LRU: tab_0 (PID 1000) should have been killed via its PGID
            # Our SessionManager now uses killpg
            mock_killpg.assert_any_call(1000, signal.SIGKILL)

            # Verify tab_0 was removed
            assert session_manager.get_session("tab_0") is None
            # Verify tab_new was added
            assert session_manager.get_session("tab_new") is not None
            # Verify session count remains 50
            assert len(session_manager.sessions) == 50
