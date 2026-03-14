import os
from unittest.mock import patch
from src.process_manager import build_terminal_command, fetch_sessions_for_host


@patch.dict(os.environ, {"SKIP_MULTIPLEXER": "true"})
def test_build_terminal_command_resume_injection_local():
    import shlex

    # When no ssh_target is provided, it runs locally
    cmd = build_terminal_command(
        None, None, "123; echo 'vulnerable'", "/tmp/.ssh", "gemini"
    )

    # Extract the shell command passed to /bin/sh
    shell_cmd = cmd[2]
    # Check that the resume parameter is properly quoted
    assert shlex.quote("123; echo 'vulnerable'") in shell_cmd


@patch.dict(os.environ, {"SKIP_MULTIPLEXER": "true"})
def test_build_terminal_command_resume_injection_ssh():
    import shlex

    # When ssh_target is provided, it runs over SSH
    cmd = build_terminal_command(
        "user@host", "/tmp/dir", "123; echo 'vulnerable'", "/tmp/.ssh", "gemini"
    )

    # Extract the command passed to SSH (wrapped in bash -ilc)
    remote_cmd = cmd[-1]

    # Since the whole remote_cmd is shlex.quoted, we need to check if the shlex.quoted resume is inside it
    # We can just check that the raw string is NOT present to ensure it was transformed/quoted
    assert "123; echo 'vulnerable'" not in remote_cmd
    # Also ensure the single quotes and semicolons are safely handled (by checking for standard shlex.quote behavior)
    assert shlex.quote(shlex.quote("123; echo 'vulnerable'"))[1:-1] in remote_cmd


@patch.dict(os.environ, {"SKIP_MULTIPLEXER": "true"})
def test_build_terminal_command_ssh_dir_injection_ssh():
    import shlex

    # Test ssh_dir is properly quoted
    cmd = build_terminal_command(
        "user@host", "my_dir; rm -rf /", "123", "/tmp/.ssh", "gemini"
    )

    remote_cmd = cmd[-1]
    expected_dir = shlex.quote("my_dir; rm -rf /")
    assert expected_dir in remote_cmd


@patch.dict(os.environ, {"SKIP_MULTIPLEXER": "true"})
def test_build_terminal_command_local_workdir_injection():
    import shlex

    # By mocking DATA_DIR we can test if local setup command properly quotes it
    with patch("os.environ.get", return_value="/data; echo 'hacked'"):
        cmd = build_terminal_command(None, None, "123", "/tmp/.ssh", "gemini")
        shell_cmd = cmd[2]

        # Check that the work_dir is quoted
        expected_dir = shlex.quote("/data; echo 'hacked'/workspace")
        assert expected_dir in shell_cmd


@patch.dict(os.environ, {"SKIP_MULTIPLEXER": "true"})
def test_build_terminal_command_gemini_bin_injection_ssh():
    import shlex

    cmd = build_terminal_command(
        "user@host", "/tmp/dir", "123", "/tmp/.ssh", "gemini; rm -rf /"
    )
    remote_cmd = cmd[-1]
    assert shlex.quote("gemini; rm -rf /") in remote_cmd


@patch.dict(os.environ, {"SKIP_MULTIPLEXER": "true"})
def test_build_terminal_command_gemini_bin_injection_local():
    import shlex

    cmd = build_terminal_command(None, None, "123", "/tmp/.ssh", "gemini; rm -rf /")
    shell_cmd = cmd[2]
    assert shlex.quote("gemini; rm -rf /") in shell_cmd


@patch("subprocess.run")
def test_fetch_sessions_for_host_gemini_bin_injection_ssh(mock_run):
    import shlex

    host = {"target": "user@host", "dir": "/tmp"}
    fetch_sessions_for_host(host, "/tmp/.ssh", gemini_bin="gemini; rm -rf /")
    cmd = mock_run.call_args[0][0]
    remote_cmd = cmd[-1]
    assert shlex.quote("gemini; rm -rf /") in remote_cmd


@patch("subprocess.run")
def test_fetch_sessions_for_host_gemini_bin_injection_local(mock_run):
    import shlex

    with patch("os.path.exists", return_value=True):
        host = {"target": None, "dir": "/tmp"}
        fetch_sessions_for_host(host, "/tmp/.ssh", gemini_bin="gemini; rm -rf /")
        cmd = mock_run.call_args[0][0]
        shell_cmd = cmd[2]
        assert shlex.quote("gemini; rm -rf /") in shell_cmd
