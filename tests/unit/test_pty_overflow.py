import pty
import os
import time


def test_pty_overflow():
    pid, fd = pty.fork()

    if pid == 0:
        # Child
        try:
            time.sleep(0.5)
            # Use raw file descriptor 0 instead of sys.stdin.fileno()
            # since pytest captures sys.stdin and it lacks fileno().
            data = os.read(0, 100000)
            os._exit(0)
        except Exception:
            os._exit(1)
    else:
        # Parent
        os.set_blocking(fd, False)
        data = b"a" * 1000 + b"\n"
        try:
            written = os.write(fd, data)
        except OSError:
            pass

        _, status = os.waitpid(pid, 0)
        os.close(fd)
        assert status == 0
