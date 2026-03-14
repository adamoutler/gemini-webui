import os
from unittest.mock import patch, MagicMock
from src.app import pty_restart, app


def test_remote_gemini_detection_missing(test_data_dir):
    app.config["DATA_DIR"] = str(test_data_dir)
    app.config["TESTING"] = True

    with app.test_request_context("/"):
        # Mock PTY and other logic to focus on remote command construction
        with patch("src.app.pty.fork") as mock_fork, patch(
            "src.app.get_config_paths"
        ) as mock_paths, patch("os.chdir"), patch("os.execvp"), patch("os._exit"):
            mock_fork.return_value = (0, 10)  # child
            mock_paths.return_value = ("/data", "/data/config.json", "/data/.ssh")

            # Trigger with SSH target
            pty_restart(
                {
                    "tab_id": "tab_remote",
                    "ssh_target": "user@remote",
                    "sid": "sid_remote",
                }
            )
            # This exercises the large block of construction logic in app.py


def test_local_project_session_fetching(test_data_dir):
    # Test the branch where /data/workspace exists
    os.makedirs(os.path.join(str(test_data_dir), "workspace"), exist_ok=True)

    with patch("src.app.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="sessions", stderr="")
        from src.app import fetch_sessions_for_host

        # Force the branch that checks for workspace
        with patch("src.app.os.path.exists", return_value=True):
            fetch_sessions_for_host({"type": "local"}, "/tmp/.ssh")
        # Verify it used /bin/sh -c or direct gemini
        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "gemini" in cmd_str
        assert "--list-sessions" in cmd_str
