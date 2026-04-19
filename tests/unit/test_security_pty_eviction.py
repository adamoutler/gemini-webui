import time
import os
import signal
from unittest.mock import patch
from src.services.session_store import SessionManager
from src.models.session import Session


def test_lru_pty_eviction():
    manager = SessionManager()
    user_id = "test_user_123"

    with patch("os.close") as mock_close, patch("os.kill") as mock_kill, patch(
        "fcntl.fcntl"
    ):
        # Create 51 sessions for the same user
        sessions = []
        for i in range(51):
            tab_id = f"tab_{i}"
            fd = i + 100
            pid = i + 1000
            session = Session(tab_id=tab_id, fd=fd, pid=pid, user_id=user_id)
            # Stagger last_seen to make session 0 the oldest
            session.last_seen = time.time() + i
            sessions.append(session)

            manager.add_session(session)

        # Verify 50 sessions remain
        remaining_sessions = manager.list_sessions(user_id)
        assert len(remaining_sessions) == 50

        # Verify oldest session (tab_0) was evicted
        assert manager.get_session("tab_0", user_id) is None

        # Verify os.close, os.kill were called for session 0 (fd=100, pid=1000)
        mock_close.assert_called_once_with(100)
        mock_kill.assert_any_call(1000, signal.SIGKILL)
        # Check that tab_1 to tab_50 are present
        for i in range(1, 51):
            assert manager.get_session(f"tab_{i}", user_id) is not None


def test_lru_eviction_multiple_users():
    manager = SessionManager()

    with patch("os.close"), patch("os.kill"), patch("os.waitpid"), patch("fcntl.fcntl"):
        # Add 49 sessions for user1
        for i in range(49):
            session = Session(
                tab_id=f"u1_tab_{i}", fd=100 + i, pid=1000 + i, user_id="user1"
            )
            manager.add_session(session)

        # Add 49 sessions for user2
        for i in range(49):
            session = Session(
                tab_id=f"u2_tab_{i}", fd=200 + i, pid=2000 + i, user_id="user2"
            )
            manager.add_session(session)

        assert len(manager.get_all_sessions()) == 98

        # Add 2 more for user1 (total 51 -> 1 eviction)
        for i in range(49, 51):
            session = Session(
                tab_id=f"u1_tab_{i}", fd=100 + i, pid=1000 + i, user_id="user1"
            )
            session.last_seen = time.time() + i
            manager.add_session(session)

        assert len(manager.list_sessions("user1")) == 50
        assert len(manager.list_sessions("user2")) == 49
        assert len(manager.get_all_sessions()) == 99
