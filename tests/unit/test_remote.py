import pytest
import json
from unittest.mock import patch, MagicMock
from src.app import app


@pytest.mark.timeout(60)
def test_remote_sessions_list(client):
    with patch("src.services.process_engine.subprocess.Popen") as mock_run:
        mock_proc = MagicMock(returncode=0)
        mock_proc.communicate.return_value = (
            """  1. SessionOne (active) [uuid1]
  2. SessionTwo (paused) [uuid2]""",
            "",
        )
        mock_run.return_value = mock_proc

        response = client.get("/api/sessions?ssh_target=user@host&ssh_dir=/tmp")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "output" in data
        assert "SessionOne" in data["output"]
        assert "SessionTwo" in data["output"]


@pytest.mark.timeout(60)
def test_remote_sessions_timeout(client):
    import subprocess

    with patch(
        "src.services.process_engine.subprocess.Popen",
        side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=45),
    ):
        response = client.get("/api/sessions?ssh_target=user@host")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "error" in data
        assert "timed out" in data["error"]
