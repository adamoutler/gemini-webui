import os
import signal
import subprocess
import eventlet
import eventlet.green.subprocess
import threading
import time
import logging
from src.shared_state import abandoned_pids, abandoned_pids_lock

logger = logging.getLogger(__name__)

managed_ptys = set()
managed_ptys_lock = threading.Lock()


def add_managed_pty(pid):
    if pid is not None:
        with managed_ptys_lock:
            managed_ptys.add(pid)


def kill_and_reap(pid):
    """Kills a process and its entire group, then reaps the zombie immediately."""
    if pid is None:
        return
    try:
        # Kill the entire process group started by setsid() in child
        # The PID is the PGID because of setsid() or start_new_session=True.
        # This will succeed even if the process leader is a reaped zombie,
        # ensuring all grandchildren are killed.
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    # Try an instantaneous reap for this specific PID (non-blocking)
    try:
        res = os.waitpid(pid, os.WNOHANG)
        wpid = res[0] if isinstance(res, tuple) else res
        if wpid == pid:
            with managed_ptys_lock:
                managed_ptys.discard(pid)
    except OSError:
        pass


reaper_event = eventlet.Event()


def sigchld_handler(signum, frame):
    if not reaper_event.ready():
        reaper_event.send()


def zombie_reaper_task(sleep_interval=5.0):
    """Event-driven, non-blocking global reaper for all dead children."""
    global reaper_event
    try:
        signal.signal(signal.SIGCHLD, sigchld_handler)
    except Exception as e:
        logger.warning(f"Could not register SIGCHLD handler: {e}")

    while True:
        try:
            # Block efficiently until SIGCHLD sets the event (or timeout as fallback)
            try:
                # eventlet.Event.wait might not support timeout directly, but if it does, handle it
                # Using eventlet.Timeout is safer for older versions
                with eventlet.Timeout(sleep_interval, False):
                    reaper_event.wait()
            except Exception:
                pass

            if reaper_event.ready():
                reaper_event.reset()

            while True:
                try:
                    # -1 means any child process. WNOHANG makes it non-blocking.
                    pid, status = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break  # No more exited children waiting to be reaped

                    logger.debug(f"Reaped zombie PID {pid} with status {status}")

                    # Remove from tracking sets if applicable
                    with managed_ptys_lock:
                        managed_ptys.discard(pid)
                    with abandoned_pids_lock:
                        abandoned_pids.discard(pid)

                except ChildProcessError:
                    break  # ECHILD: No child processes exist at all
                except OSError as e:
                    logger.error(f"OSError in reaper loop: {e}")
                    break
        except Exception as e:
            logger.error(f"Fatal error in global reaper: {e}")
            eventlet.sleep(1)  # Backoff on fatal error


def cleanup_orphaned_ptys(app, session_manager, env_config):
    """Cleanup orphaned sessions based on ORPHANED_SESSION_TTL."""
    is_testing = app.config.get("TESTING") or env_config.BYPASS_AUTH_FOR_TESTING
    while True:
        try:
            # Use config TTL if available, otherwise fallback to 2s in testing or None (disabled) in production
            ttl = app.config.get("ORPHANED_SESSION_TTL")
            if ttl is None:
                ttl = env_config.ORPHANED_SESSION_TTL
            if ttl is None:
                ttl = 2 if is_testing else None

            if ttl is not None:
                now = time.time()
                for session in session_manager.get_all_sessions():
                    if (
                        session.orphaned_at is not None
                        and (now - session.orphaned_at) > ttl
                    ):
                        kill_and_reap(session.pid)
                        session_manager.remove_session(session.tab_id)
        except Exception as e:
            logger.error(f"Error in cleanup_orphaned_ptys: {e}")

        # In testing, we sleep briefly to allow rapid reaping of leaking processes
        eventlet.sleep(1 if is_testing else 60)
        if is_testing and os.environ.get("GEMWEBUI_HARNESS") != "1":
            break


def apply_subprocess_monkey_patch():
    """Manually patch subprocess.run to handle GreenletExit and prevent zombie processes."""

    def safe_subprocess_run(*popenargs, **kwargs):
        timeout = kwargs.pop("timeout", None)
        input_data = kwargs.pop("input", None)
        check = kwargs.pop("check", False)
        is_new_session = kwargs.get("start_new_session", False)
        if kwargs.pop("capture_output", False):
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE

        with eventlet.green.subprocess.Popen(*popenargs, **kwargs) as process:
            try:
                text_mode = kwargs.get("text", False)
                if input_data is not None and text_mode and isinstance(input_data, str):
                    input_data = input_data.encode("utf-8")

                stdout, stderr = process.communicate(input=input_data, timeout=timeout)

                if text_mode:
                    if isinstance(stdout, bytes):
                        stdout = stdout.decode("utf-8", "replace")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", "replace")

                retcode = process.poll()
                if check and retcode:
                    raise eventlet.green.subprocess.CalledProcessError(
                        retcode, process.args, output=stdout, stderr=stderr
                    )
                return eventlet.green.subprocess.CompletedProcess(
                    process.args, retcode, stdout, stderr
                )
            except eventlet.green.subprocess.TimeoutExpired:
                # Let TimeoutExpired propagate normally without adding to abandoned_pids,
                # but kill the process first to prevent zombies.
                try:
                    if is_new_session:
                        try:
                            if os.getpgid(process.pid) != os.getpgrp():
                                try:
                                    if os.getpgid(process.pid) != os.getpgrp():
                                        os.killpg(
                                            os.getpgid(process.pid), signal.SIGKILL
                                        )
                                    else:
                                        os.kill(process.pid, signal.SIGKILL)
                                except OSError:
                                    pass
                            else:
                                os.kill(process.pid, signal.SIGKILL)
                        except OSError:
                            process.kill()
                    else:
                        process.kill()
                    process.wait(timeout=1)
                except OSError:
                    pass
                except eventlet.green.subprocess.TimeoutExpired:
                    with abandoned_pids_lock:
                        abandoned_pids.add(process.pid)
                raise
            except BaseException:
                try:
                    if is_new_session:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except OSError:
                            try:
                                os.kill(process.pid, signal.SIGKILL)
                            except OSError:
                                pass
                    else:
                        process.kill()
                except OSError:
                    pass
                with abandoned_pids_lock:
                    abandoned_pids.add(process.pid)
                raise

    subprocess.run = safe_subprocess_run
    eventlet.green.subprocess.run = safe_subprocess_run
