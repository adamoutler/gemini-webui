import pytest
from src.gateways.terminal_socket import pty_restart
from unittest.mock import patch, MagicMock
from src.services.process_engine import fetch_sessions_for_host, validate_ssh_target


@pytest.mark.timeout(60)
def test_fetch_sessions_for_host_local():
    host = {"type": "local", "target": None, "dir": None}
    with patch("src.services.process_engine.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="  1. Local (test) [uuid]", stderr=""
        )

        result = fetch_sessions_for_host(host, "/tmp/.ssh")
        assert result["output"] == "  1. Local (test) [uuid]"
        assert mock_run.called


@pytest.mark.timeout(60)
def test_fetch_sessions_for_host_ssh():
    host = {"type": "ssh", "target": "user@remote", "dir": "~/myproject"}
    with patch("src.services.process_engine.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="  1. Remote (test) [uuid]", stderr=""
        )

        result = fetch_sessions_for_host(host, "/tmp/.ssh")
        assert result["output"] == "  1. Remote (test) [uuid]"

        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "ssh" in cmd
        assert "user@remote" in cmd
        remote_bash_cmd = cmd[-1]
        assert "bash -ilc" in remote_bash_cmd
        # We don't want a non-interactive shell because gemini needs a proper environment
        # to output session text (no screen-clear ANSI codes due to stdin=DEVNULL).
        assert "~/myproject" in remote_bash_cmd or "myproject" in remote_bash_cmd
        assert "gemini --list-sessions" in remote_bash_cmd


@pytest.mark.timeout(60)
def test_validate_ssh_target_invalid():
    assert not validate_ssh_target("user@host; rm -rf /")
    assert validate_ssh_target("user@192.168.1.100")
    assert validate_ssh_target("user@host.com:2222")


@patch("pty.fork")
@patch("os.closerange")
@patch("os.execvpe")
@patch("os._exit")
@patch("shutil.which", return_value=None)
@pytest.mark.timeout(60)
def test_pty_restart_local_cmd(
    mock_which, mock_exit, mock_execvpe, mock_closerange, mock_fork
):
    # Simulate being the child process
    mock_fork.return_value = (0, 1)  # child_pid=0, fd=1

    data = {"tab_id": "test_tab", "resume": True}

    # Needs to run in app context to access session
    from src.app import app

    with app.test_request_context("/"):
        pty_restart(data)

    mock_execvpe.assert_called_once()
    cmd = mock_execvpe.call_args[0][1]
    assert cmd[0] == "/bin/sh"
    assert "gemini -r" in cmd[2]
    assert "WARNING: Persistence volume not found" in cmd[2]


@patch("pty.fork")
@patch("os.closerange")
@patch("os.execvpe")
@patch("os._exit")
@patch("shutil.which", return_value=None)
@pytest.mark.timeout(60)
def test_pty_restart_ssh_cmd(
    mock_which, mock_exit, mock_execvpe, mock_closerange, mock_fork
):
    # Simulate being the child process
    mock_fork.return_value = (0, 1)  # child_pid=0, fd=1

    data = {
        "tab_id": "test_tab",
        "resume": True,
        "ssh_target": "user@remote.com",
        "ssh_dir": "~/dev/project",
    }

    from src.app import app

    with app.test_request_context("/"):
        pty_restart(data)

    mock_execvpe.assert_called_once()
    cmd = mock_execvpe.call_args[0][1]
    assert cmd[0] == "ssh"
    assert "user@remote.com" in cmd

    remote_cmd = cmd[-1]
    assert "bash -ilc" in remote_cmd
    assert "gemini -r" in remote_cmd
    assert "cd ~" in remote_cmd
    assert "dev/project" in remote_cmd


@pytest.mark.timeout(60)
def test_build_terminal_command_resume_new():
    from src.services.process_engine import build_terminal_command

    # Test local
    cmd = build_terminal_command(None, None, "new", "/tmp/.ssh")
    cmd_str = " ".join(cmd)
    assert "gemini -r" not in cmd_str

    # Test SSH
    cmd_ssh = build_terminal_command("user@host", "~/dir", "new", "/tmp/.ssh")
    remote_cmd = cmd_ssh[-1]
    assert "gemini -r" not in remote_cmd


@pytest.mark.timeout(60)
def test_build_terminal_command_resume_id():
    from src.services.process_engine import build_terminal_command

    # Test local
    cmd = build_terminal_command(None, None, "123", "/tmp/.ssh")
    cmd_str = " ".join(cmd)
    assert "gemini -r 123" in cmd_str

    # Test SSH
    cmd_ssh = build_terminal_command("user@host", "~/dir", "123", "/tmp/.ssh")
    remote_cmd = cmd_ssh[-1]
    assert "gemini -r 123" in remote_cmd


@pytest.mark.timeout(60)
def test_build_terminal_command_resume_true():
    from src.services.process_engine import build_terminal_command

    # Test local
    cmd = build_terminal_command(None, None, True, "/tmp/.ssh")
    cmd_str = " ".join(cmd)
    assert "gemini -r" in cmd_str
    assert "gemini -r True" not in cmd_str
    assert "gemini -r true" not in cmd_str

    # Test SSH
    cmd_ssh = build_terminal_command("user@host", "~/dir", True, "/tmp/.ssh")
    remote_cmd = cmd_ssh[-1]
    assert "gemini -r" in remote_cmd
    assert "gemini -r True" not in remote_cmd
    assert "gemini -r true" not in remote_cmd
