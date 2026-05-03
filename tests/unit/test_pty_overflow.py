import pytest
import pty
import os
import subprocess
import sys


@pytest.mark.timeout(60)
def test_pty_overflow():
    master_fd, slave_fd = pty.openpty()

    # Run a simple child process that sleeps, then reads
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time, os; time.sleep(0.5); os.read(0, 100000)"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)  # close slave in parent

    os.set_blocking(master_fd, False)
    data = b"a" * 1000 + b"\n"
    try:
        os.write(master_fd, data)
    except OSError:
        pass

    proc.wait()
    os.close(master_fd)
    assert proc.returncode == 0
