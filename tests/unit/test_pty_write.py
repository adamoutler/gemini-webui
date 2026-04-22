import pytest
import pty
import os


@pytest.mark.timeout(60)
def test_pty_write_buffer_size():
    master, slave = pty.openpty()
    os.set_blocking(master, False)

    # write 20000 chars
    data = b"a" * 20000
    try:
        written = os.write(master, data)
        assert written > 0
    except BlockingIOError:
        pass  # Expected if buffer is smaller than 20k and non-blocking

    os.close(master)
    os.close(slave)
