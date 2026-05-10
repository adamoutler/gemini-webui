from unittest.mock import patch, MagicMock

import pytest
from src.app import create_app
from src.services.terminal_service import TerminalService
from src.services.remote_fs import download_from_remote, upload_to_remote


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["BYPASS_AUTH_FOR_TESTING"] = True
    with app.test_client() as client:
        yield client


@patch("src.routes.api.os.path.isfile")
def test_get_file_stack_trace_exposure(mock_isfile, client):
    # Simulate an unexpected exception during file retrieval
    mock_isfile.side_effect = Exception("Internal Secret Error Details 123")

    # Needs to be an authenticated session or bypass auth if TESTING
    with client.session_transaction() as sess:
        sess["username"] = "testuser"
        sess["authenticated"] = True

    response = client.get("/api/download/some_file.txt")

    assert response.status_code == 500
    data = response.get_json()
    assert data["status"] == "error"
    # Ensure the exact exception text is NOT leaked
    assert "Internal Secret Error Details 123" not in data["message"]
    assert "An internal error occurred" in data["message"]


@patch("src.routes.api.get_descendant_processes")
@patch("src.routes.api.os.killpg")
@patch("src.routes.api.os.kill")
def test_kill_process_stack_trace_exposure(
    mock_kill, mock_killpg, mock_get_descendants, client
):
    # Mock a child process to pass the permission check
    mock_get_descendants.return_value = [{"pid": 9999, "cmdline": ["sleep", "10"]}]

    # Simulate OSError in both killpg and kill
    mock_killpg.side_effect = OSError("Internal OSError detail pg")
    mock_kill.side_effect = OSError("Internal OSError detail pid")

    with client.session_transaction() as sess:
        sess["username"] = "testuser"
        sess["authenticated"] = True

    response = client.delete("/api/processes/9999")

    assert response.status_code == 500
    data = response.get_json()
    # Ensure internal exception details are NOT leaked
    assert "Internal OSError detail pg" not in data["error"]
    assert "Internal OSError detail pid" not in data["error"]
    assert "Failed to kill process due to an internal error." in data["error"]


@patch("subprocess.run")
def test_terminal_service_command_injection_mitigation(mock_run):
    # Check that shell=False is explicitly passed to subprocess.run
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    response, status_code = TerminalService.execute_command_sync(
        ssh_target="user@host", ssh_dir="/tmp/ssh", prompt="hello"
    )

    assert status_code == 200
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("shell") is False


@patch("subprocess.run")
@patch("src.services.remote_fs.tempfile.mkstemp")
def test_remote_fs_get_file_command_injection_mitigation(mock_mkstemp, mock_run):
    mock_mkstemp.return_value = (1, "/tmp/local_file")
    mock_run.return_value = MagicMock(returncode=0)

    download_from_remote(
        "remote_file.txt", "user@host", "/tmp/ssh", "mock_gemini_cli.py"
    )

    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("shell") is False


@patch("subprocess.run")
def test_remote_fs_put_file_command_injection_mitigation(mock_run):
    mock_run.return_value = MagicMock(returncode=0)

    upload_to_remote(
        "local.txt", "remote.txt", "user@host", "/tmp/ssh", "mock_gemini_cli.py"
    )

    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("shell") is False
