import pytest
import json
from unittest.mock import patch, MagicMock
from src.app import app


def test_remote_sessions_list(client):
    with patch("src.process_manager.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""  1. SessionOne (active) [uuid1]
  2. SessionTwo (paused) [uuid2]""",
            stderr="",
        )

        response = client.get("/api/sessions?ssh_target=user@host&ssh_dir=/tmp")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "output" in data
        assert "SessionOne" in data["output"]
        assert "SessionTwo" in data["output"]


def test_remote_sessions_timeout(client):
    import subprocess

    with patch(
        "src.process_manager.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=45),
    ):
        response = client.get("/api/sessions?ssh_target=user@host")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "error" in data
        assert "timed out" in data["error"]
