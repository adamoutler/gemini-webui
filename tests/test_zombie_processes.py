import pty
import os
import time
from unittest.mock import patch

from src.app import (
    session_manager,
    read_and_forward_pty_output,
    zombie_reaper_task,
    add_managed_pty,
    managed_ptys_lock,
)
from src.session_manager import Session


def test_pty_reader_reaps_zombies():
    tab_id = "test-zombie"
    pid, fd = pty.fork()
    if pid == 0:
        # Child process exits immediately
        os._exit(0)

    add_managed_pty(pid)
    session = Session(tab_id, fd, pid, "user1")
    session_manager.add_session(session)

    # Wait briefly for child to exit
    time.sleep(0.1)

    # Actually read_and_forward_pty_output loops forever until sleep, so we'll just mock select to raise OSError
    # to simulate the EIO when the PTY closes on the other side
    def mock_sleep(*args, **kwargs):
        if not hasattr(mock_sleep, "called"):
            mock_sleep.called = True
            return
        raise StopIteration("Stop Loop")

    with patch("src.app.select.select", side_effect=OSError("Test EIO")):
        with patch("src.app.socketio.sleep", side_effect=mock_sleep):
            try:
                read_and_forward_pty_output()
            except StopIteration:
                pass

    # Now run the zombie reaper task manually for one iteration
    with patch("src.app.socketio.sleep", side_effect=StopIteration("Stop Loop")):
        try:
            zombie_reaper_task()
        except StopIteration:
            pass

    # Now verify the process was reaped. If not reaped, waitpid with WNOHANG will return the PID.
    # If reaped, waitpid will raise ChildProcessError
    try:
        wpid, status = os.waitpid(pid, os.WNOHANG)
        # If wpid == pid, it was NOT reaped!
        assert (
            wpid == 0 or wpid != pid
        ), f"Process {pid} was not reaped and is a zombie!"
    except ChildProcessError:
        # Reaped successfully!
        pass
    except OSError as e:
        # Erno 10 is ECHILD (No child processes)
        assert e.errno == 10, f"Unexpected OSError: {e}"
