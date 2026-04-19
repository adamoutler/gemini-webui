import pytest
import os
import subprocess
import getpass
from src.services.process_engine import SSHConnectionManager, build_ssh_args


@pytest.mark.timeout(30)
def test_real_ssh_multiplexing():
    # Only run this test if we can passwordlessly ssh to localhost
    user = getpass.getuser()
    try:
        subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=no",
                f"{user}@localhost",
                "echo 'ready'",
            ],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pytest.skip("Passwordless SSH to localhost is not available")

    # Let's clean up any existing socket
    socket_path = SSHConnectionManager.get_socket_path(user, "localhost", 22)
    if os.path.exists(socket_path):
        os.remove(socket_path)

    # 1. First connection: should take some time, create socket
    args = build_ssh_args(f"{user}@localhost", os.path.expanduser("~/.ssh"))
    cmd1 = args + [f"{user}@localhost", "echo", "first"]

    # We must use control path args that are in args
    res1 = subprocess.run(cmd1, capture_output=True, text=True)

    assert res1.returncode == 0
    assert "first" in res1.stdout
    assert os.path.exists(socket_path), f"Socket not created at {socket_path}"

    # 2. Second connection: should reuse the socket, run faster, and work even if we pass a bad key
    # Wait, the multiplexing uses the existing connection, so it doesn't do auth again.
    cmd2 = args + [f"{user}@localhost", "echo", "second"]
    res2 = subprocess.run(cmd2, capture_output=True, text=True)

    assert res2.returncode == 0
    assert "second" in res2.stdout

    # 3. Test check_and_recover_connection detects live connection
    SSHConnectionManager.check_and_recover_connection(user, "localhost", 22)
    assert os.path.exists(socket_path), "Socket should still exist after health check"

    # 4. Now forcefully exit the multiplexed connection
    exit_cmd = [
        "ssh",
        "-O",
        "exit",
        "-o",
        f"ControlPath={socket_path}",
        f"{user}@localhost",
    ]
    subprocess.run(exit_cmd, capture_output=True)

    # After exit, check_and_recover should realize it's dead, and delete the socket
    if os.path.exists(socket_path):
        SSHConnectionManager.check_and_recover_connection(user, "localhost", 22)
        assert not os.path.exists(
            socket_path
        ), "Socket should have been removed after detecting dead connection"
