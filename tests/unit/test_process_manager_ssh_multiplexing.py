import pytest
from unittest.mock import patch, MagicMock

# We will need to implement SSHConnectionManager in src/process_manager.py
from src.process_manager import SSHConnectionManager, build_ssh_args, SSH_SOCKET_DIR


def test_get_socket_path():
    path = SSHConnectionManager.get_socket_path("user", "host", 22)
    assert str(SSH_SOCKET_DIR) in path
    assert "user@host_22.sock" in path


def test_get_base_ssh_args():
    args = SSHConnectionManager.get_base_ssh_args("user", "host", 22)
    assert "-o" in args
    assert "ControlMaster=auto" in args
    assert "ControlPersist=10m" in args
    assert any("ControlPath=" in arg for arg in args)


@patch("src.process_manager.subprocess.run")
@patch("src.process_manager.os.path.exists")
def test_check_and_recover_connection_dead(mock_exists, mock_run):
    mock_exists.return_value = True
    # First run is check, which raises TimeoutExpired
    import subprocess

    mock_run.side_effect = [
        subprocess.TimeoutExpired(cmd="ssh", timeout=5),
        MagicMock(returncode=0),
    ]

    SSHConnectionManager.check_and_recover_connection("user", "host", 22)

    assert mock_run.call_count == 2
    # Check that the second call was the exit command
    exit_call_args = mock_run.call_args_list[1][0][0]
    assert "-O" in exit_call_args
    assert "exit" in exit_call_args


@patch("src.process_manager.subprocess.run")
@patch("src.process_manager.os.path.exists")
def test_check_and_recover_connection_healthy(mock_exists, mock_run):
    mock_exists.return_value = True
    mock_run.return_value = MagicMock(returncode=0)

    SSHConnectionManager.check_and_recover_connection("user", "host", 22)

    assert mock_run.call_count == 1
    check_call_args = mock_run.call_args_list[0][0][0]
    assert "-O" in check_call_args
    assert "check" in check_call_args
