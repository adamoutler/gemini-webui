import os
import signal
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.getcwd())


class TestZombieFix(unittest.TestCase):
    def test_session_manager_replaces_and_kills_old_pid(self):
        from src.session_manager import SessionManager, Session

        sm = SessionManager()

        # Mock os.killpg and os.getpgid and os.close
        with patch("src.session_manager.os.killpg") as mock_killpg, patch(
            "src.session_manager.os.getpgid"
        ) as mock_getpgid, patch("src.session_manager.os.close") as mock_close:
            mock_getpgid.return_value = 100

            s1 = Session("tab1", None, 100, "user1")
            sm.add_session(s1)

            s2 = Session("tab1", None, 101, "user1")
            # We don't pass on_remove here to test the default kill logic in add_session
            sm.add_session(s2)

            # Should have killed s1.pid (100)
            mock_killpg.assert_called_with(100, signal.SIGKILL)
            mock_close.assert_called_with(10)
            self.assertEqual(sm.get_session("tab1").pid, 101)

    @patch("src.process_manager.subprocess.run")
    def test_fetch_sessions_has_timeout_and_session_group(self, mock_run):
        from src.process_manager import fetch_sessions_for_host

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        fetch_sessions_for_host({"type": "local"}, "/tmp")

        args, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 15)
        self.assertTrue(kwargs.get("start_new_session"))


if __name__ == "__main__":
    unittest.main()
