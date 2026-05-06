import subprocess
from src.services.terminal_service import TerminalService


def test_start_session_invalid_target():
    service = TerminalService()
    resp = service.start_session(
        tab_id="tab2",
        user_id="user1",
        ssh_target="invalid target!",
        ssh_dir="",
        resume=False,
        cols=80,
        rows=24,
        env_vars={},
    )
    assert "Invalid SSH target format" in str(resp)


def test_execute_command_invalid():
    service = TerminalService()
    result, status = service.execute_command_sync(
        "non_existent_tab", "ls", prompt="mock_prompt"
    )
    assert status in (400, 404)


class MockResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_execute_command_sync_local(monkeypatch):
    # Mock subprocess.run to avoid actually executing
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(returncode=0, stdout="success", stderr=""),
    )
    res, code = TerminalService.execute_command_sync(None, None, "ls -la")
    assert code == 200
    assert res["status"] == "success"
    assert res["data"]["stdout"] == "success"


def test_execute_command_sync_local_error(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(returncode=1, stdout="", stderr="error"),
    )
    res, code = TerminalService.execute_command_sync(None, None, "ls -la")
    assert code == 500
    assert res["status"] == "error"


def test_execute_command_sync_local_timeout(monkeypatch):
    def mock_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ls", timeout=60)

    monkeypatch.setattr("subprocess.run", mock_timeout)
    res, code = TerminalService.execute_command_sync(None, None, "ls -la")
    assert code == 504


def test_execute_command_sync_ssh(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockResult(
            returncode=0, stdout="ssh success", stderr=""
        ),
    )
    res, code = TerminalService.execute_command_sync(
        "user@192.168.1.1:2222", "/dir", "ls -la"
    )
    assert code == 200
    assert res["status"] == "success"
    assert res["data"]["stdout"] == "ssh success"


def test_execute_command_sync_ssh_invalid():
    res, code = TerminalService.execute_command_sync("invalid_target", "/dir", "ls")
    assert code == 400
    assert res["status"] == "error"
