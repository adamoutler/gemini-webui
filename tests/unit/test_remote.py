import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.mark.timeout(60)
def test_remote_sessions_list(client):
    from src.services.process_engine import fetch_sessions_for_host
    from src.shared_state import session_results_cache_lock, session_results_cache

    with patch("src.services.process_engine.subprocess.Popen") as mock_run:
        mock_proc = MagicMock(returncode=0)
        mock_proc.communicate.return_value = (
            """  1. SessionOne (active) [uuid1]
  2. SessionTwo (paused) [uuid2]""",
            "",
        )
        # Mock pid to prevent errors
        mock_proc.pid = 1234
        mock_run.return_value = mock_proc

        # Simulate the background poller running once
        host = {"target": "user@host", "dir": "/tmp"}
        fetch_sessions_for_host(host, "/tmp")

        # Now test the frontend API
        response = client.get("/api/sessions?ssh_target=user@host&ssh_dir=/tmp")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "output" in data
        assert "SessionOne" in data["output"]


@pytest.mark.timeout(60)
def test_remote_sessions_timeout(client):
    import subprocess
    from src.services.process_engine import fetch_sessions_for_host

    with patch(
        "src.services.process_engine.subprocess.Popen",
        side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=45),
    ):
        # Simulate background poller
        host = {"target": "user@host", "dir": ""}
        fetch_sessions_for_host(host, "/tmp")

        from src.shared_state import session_results_cache

        print("CACHE KEYS:", session_results_cache.keys())
        print("CACHE VALUE:", session_results_cache.get("ssh:user@host:"))

        response = client.get("/api/sessions?ssh_target=user@host")
        # Since it's a 504 the API returns 504
        assert response.status_code == 504
        data = json.loads(response.data)
        assert "error" in data
        assert "timed out" in data["error"].lower()
