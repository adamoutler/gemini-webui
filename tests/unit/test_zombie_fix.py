import pytest
import os
import signal
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.getcwd())


class TestZombieFix(unittest.TestCase):
    @pytest.mark.timeout(60)
    def test_session_manager_replaces_and_kills_old_pid(self):
        from src.services.session_store import SessionManager
        from src.models.session import Session

        sm = SessionManager()

        # Mock os.killpg and os.getpgid and os.close and fcntl.fcntl
        with patch("src.services.session_store.os.killpg") as mock_killpg, patch(
            "src.services.session_store.os.getpgid"
        ) as mock_getpgid, patch(
            "src.services.session_store.os.close"
        ) as mock_close, patch("src.models.session.fcntl.fcntl") as mock_fcntl:
            mock_getpgid.return_value = 100

            s1 = Session("tab1", 10, 100, "user1")
            sm.add_session(s1)

            s2 = Session(
                "tab1", 11, 101, "user1"
            )  # We don't pass on_remove here to test the default kill logic in add_session
            sm.add_session(s2)

            # Should have killed s1.pid (100)
            mock_killpg.assert_called_with(100, signal.SIGKILL)
            mock_close.assert_called_with(10)
            self.assertEqual(sm.get_session("tab1").pid, 101)

    @patch("src.services.process_engine.subprocess.Popen")
    @pytest.mark.timeout(60)
    def test_fetch_sessions_has_timeout_and_session_group(self, mock_run):
        from src.services.process_engine import fetch_sessions_for_host

        mock_run.return_value = MagicMock(pid=123, returncode=0)

        mock_run.return_value.communicate.return_value = ("", "")

        fetch_sessions_for_host({"type": "local"}, "/tmp")

        args, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 15)
        self.assertTrue(kwargs.get("start_new_session"))


if __name__ == "__main__":
    unittest.main()
