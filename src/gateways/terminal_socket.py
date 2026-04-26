import os
import struct
import fcntl
import termios
import select
import errno
import pty
import time
import threading
import shlex
import logging

from flask import request, session, current_app
from flask_wtf.csrf import validate_csrf, ValidationError
from flask_socketio import ConnectionRefusedError, join_room

from src.extensions import socketio
from src.config import env_config, get_config, get_config_paths
from src.services.session_store import session_manager
from src.shared_state import (
    active_fake_sockets,
    active_fake_sockets_lock,
    ephemeral_sessions,
    session_results_cache,
    session_results_cache_lock,
)
from src.services.process_engine import fetch_sessions_for_host, build_terminal_command
from src.app import kill_and_reap, add_managed_pty, IDENTIFICATION_REGEX, app
from src.models.session import Session

logger = logging.getLogger(__name__)
GEMINI_BIN = env_config.GEMINI_BIN


@socketio.on("connect")
def handle_connect(auth=None):
    from flask import request as socket_request

    sid = getattr(socket_request, "sid", None)
    from flask_wtf.csrf import validate_csrf, ValidationError

    auth = auth or {}
    csrf_token = auth.get("csrf_token")

    try:
        if current_app.config.get("WTF_CSRF_ENABLED", True):
            validate_csrf(csrf_token)
            current_app.logger.debug("CSRF validation passed")
        else:
            logger.info("CSRF validation disabled via config")
    except ValidationError as e:
        current_app.logger.debug(
            f"CSRF validation failed (expected during token refresh): {e}"
        )
        raise ConnectionRefusedError("invalid_csrf")

    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    logger.debug(f"handle_connect: user_id={user_id}")
    if user_id and sid:
        logger.debug(
            f"handle_connect: Attempting join_room user_{user_id} for SID {sid}"
        )
        join_room(f"user_{user_id}")
        logger.debug(f"SID {sid} joined user room user_{user_id}")

    if env_config.BYPASS_AUTH_FOR_TESTING:
        return True

    if not session.get("authenticated"):
        return False
    return True


@socketio.on("terminate_session")
def on_terminate_session(data):
    from flask import request as socket_request
    import os

    sid = getattr(socket_request, "sid", None)
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )

    tab_id = data.get("tab_id")
    if not tab_id:
        socketio.emit("error", {"message": "tab_id is required"}, room=sid)
        return

    old_session = session_manager.remove_session(tab_id, user_id)

    if old_session:
        logger.info(f"Socket request to terminate session {tab_id} by user {user_id}")

        if old_session.pid is not None:
            kill_and_reap(old_session.pid)

        if getattr(old_session, "fd", None) is not None:
            try:
                os.close(old_session.fd)
            except OSError:
                pass

        if tab_id in ephemeral_sessions:
            ephemeral_sessions.pop(tab_id, None)

        with active_fake_sockets_lock:
            active_fake_sockets.pop(tab_id, None)

        socketio.emit("session-terminated", {"tab_id": tab_id}, room=tab_id)

        if session_manager.persistence:
            persisted = session_manager.persistence.load()
            user_persisted = {
                tid: s for tid, s in persisted.items() if s.get("user_id") == user_id
            }
            socketio.emit("sync-tabs", user_persisted, room=f"user_{user_id}")


@socketio.on("disconnect")
def handle_disconnect():
    sid = getattr(request, "sid", None)
    tab_id = session_manager.sid_to_tabid.get(sid)
    if tab_id:
        session_manager.orphan_session(tab_id, sid)

    with active_fake_sockets_lock:
        for t_id, active_sid in list(active_fake_sockets.items()):
            if active_sid == sid:
                logger.info(
                    f"Ephemeral session {t_id} disconnected, purging to prevent reuse."
                )
                active_fake_sockets.pop(t_id, None)
                ephemeral_sessions.pop(t_id, None)

    if tab_id:
        session_manager.orphan_session(tab_id)
        logger.info(f"Session {tab_id} orphaned on disconnect (sid: {sid})")


def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception as e:
        logger.error(f"Failed to set winsize on fd {fd}: {e}")


def session_output_reader(tab_id):
    """Background task to read output from a specific session's PTY."""
    session_obj = session_manager.get_session(tab_id)
    if not session_obj:
        return

    max_read_bytes = 1024 * 20
    decoder = session_obj.decoder
    fd = session_obj.fd

    try:
        while getattr(session_obj, "active", True):
            # Eventlet's monkey-patched os.read will yield to the hub
            # if O_NONBLOCK is set and data is not ready.
            # Even without O_NONBLOCK, it should yield if it blocks.
            try:
                # Use select to avoid calling os.read when no data is ready,
                # which would yield via trampoline. This keeps the hub efficient.
                (data_ready, _, _) = select.select([fd], [], [], 0.1)
                if not getattr(session_obj, "active", True):
                    break
                if data_ready:
                    output = os.read(fd, max_read_bytes)
                    if not output:  # EOF
                        break

                    decoded_output = decoder.decode(output)
                    if decoded_output:
                        if "\x1b[" in decoded_output and "c" in decoded_output:
                            filtered_output = IDENTIFICATION_REGEX.sub(
                                "", decoded_output
                            )
                        else:
                            filtered_output = decoded_output

                        if filtered_output:
                            session_obj.append_buffer(filtered_output)
                            socketio.emit(
                                "pty-output", {"output": filtered_output}, room=tab_id
                            )
                else:
                    # No data ready, yield to the hub
                    socketio.sleep(0.01)
            except (OSError, IOError) as e:
                if getattr(e, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK):
                    socketio.sleep(0.01)
                    continue
                break
    except Exception as e:
        logger.error(f"Error in session output reader for {tab_id}: {e}")
    finally:
        logger.info(f"Session reader for {tab_id} exiting, cleaning up")
        # Ensure the session is removed from manager if reader exits organically
        if getattr(session_obj, "active", True):
            session_manager.remove_session(tab_id)
            if tab_id in ephemeral_sessions:
                ephemeral_sessions.pop(tab_id)
            if session_obj and session_obj.pid is not None:
                kill_and_reap(session_obj.pid)
            socketio.emit("session-dropped", {"tab_id": tab_id}, room=tab_id)


def background_session_preloader():
    """Continuously polls session state and broadcasts to clients."""
    run_once = False
    while True:
        if app.config.get("TESTING") and run_once:
            break
        run_once = True
        try:
            hosts = get_config().get("HOSTS", [])
            for host in hosts:
                key = f"{host.get('type')}:{host.get('target', 'local')}:{host.get('dir', '')}"
                _, _, ssh_dir_path = get_config_paths()
                res = fetch_sessions_for_host(host, ssh_dir_path, GEMINI_BIN)
                with session_results_cache_lock:
                    session_results_cache[key] = res

                socketio.emit(
                    "sessions_updated", {"host": host, "cache_key": key, "data": res}
                )
        except Exception as e:
            logger.error(f"Background polling error: {e}")
        socketio.sleep(10)


@socketio.on("join_room")
def on_join_room(data):
    from flask import request as socket_request

    sid = getattr(socket_request, "sid", None)
    tab_id = data.get("tab_id")
    if tab_id:
        if sid:
            join_room(tab_id)
            logger.debug(f"SID {sid} joined room {tab_id}")

        # Trigger a global sync for this user to ensure they have the full tab list
        user_id = session.get("user_id") or (
            "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
        )
        if user_id:
            if session_manager.persistence:
                persisted = session_manager.persistence.load()
                # ONLY sync if this tab is already known, or if we have other tabs.
                # If this is a brand new tab, pty_restart will handle the sync.
                if tab_id in persisted or len(persisted) > 0:
                    user_persisted = {
                        tid: s
                        for tid, s in persisted.items()
                        if s.get("user_id") == user_id
                    }
                    socketio.emit("sync-tabs", user_persisted, room=f"user_{user_id}")


@socketio.on("update_title")
def update_title(data):
    sid = getattr(request, "sid", None)
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    tab_id = data.get("tab_id") or session_manager.sid_to_tabid.get(sid)
    title = data.get("title")
    user_named = data.get("user_named", False)
    if tab_id and title:
        session_manager.update_title(tab_id, title, user_id, user_named)


@socketio.on("pty-input")
def pty_input(data):
    from flask import request as socket_request

    sid = getattr(socket_request, "sid", None)
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    # Get tab_id from the session mapping
    tab_id = session_manager.sid_to_tabid.get(sid)
    session_obj = session_manager.get_session(tab_id, user_id)
    if session_obj:
        session_obj.last_seen = time.time()
        input_data = data.get("input", "")
        if not input_data:
            return
        # Filter out terminal identification responses
        if input_data.startswith("\x1b[?") and input_data.endswith("c"):
            return
        # os.write will yield to the hub if O_NONBLOCK is set and buffer is full
        os.write(session_obj.fd, input_data.encode())


@socketio.on("pty-resize")
def pty_resize(data):
    sid = getattr(request, "sid", None)
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    tab_id = session_manager.sid_to_tabid.get(sid)
    session_obj = session_manager.get_session(tab_id, user_id)
    if session_obj:
        try:
            set_winsize(session_obj.fd, data["rows"], data["cols"])
        except Exception as e:
            logger.warning(f"Failed to set winsize on fd {session_obj.fd}: {e}")


@socketio.on("restart")
def pty_restart(data):
    from flask import request as socket_request

    sid = getattr(socket_request, "sid", None)
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    tab_id = data.get("tab_id")
    mode = data.get("mode")

    if mode == "fake":
        ephemeral_id = data.get("resume")
        if ephemeral_id in ephemeral_sessions:
            tab_id = ephemeral_id

    if not tab_id:
        return

    # Automatically join the room for this tab if in a real Socket.io context
    if sid:
        join_room(tab_id)

    ssh_target = data.get("ssh_target")
    is_fake = (mode == "fake") or (tab_id in ephemeral_sessions)
    executable_override = None
    if is_fake:
        if tab_id not in ephemeral_sessions:
            socketio.emit(
                "pty-output",
                {
                    "output": "\r\n\x1b[31m[Error: Invalid or expired ephemeral session. Please start a fresh test.]\x1b[0m\r\n"
                },
                room=sid,
            )
            return

        session_info = ephemeral_sessions[tab_id]
        if session_info.get("used"):
            socketio.emit(
                "pty-output",
                {
                    "output": "\r\n\x1b[31m[Error: This ephemeral session has already been used.]\x1b[0m\r\n"
                },
                room=sid,
            )
            return

        with active_fake_sockets_lock:
            if tab_id in active_fake_sockets and active_fake_sockets[tab_id] != sid:
                logger.warning(
                    f"Rejecting overlapping connection to ephemeral session {tab_id}"
                )
                socketio.emit(
                    "pty-output",
                    {
                        "output": "\r\n\x1b[31m[Error: This ephemeral session is already active in another window.]\x1b[0m\r\n"
                    },
                    room=sid,
                )
                return
            active_fake_sockets[tab_id] = sid

        session_info["used"] = True
        executable_base = session_info.get(
            "executable", "python3 src/mock_gemini_cli.py"
        )
        scenario = session_info.get("args", "default")
        executable_override = f"{executable_base} --scenario {shlex.quote(scenario)}"

    reclaim = data.get("reclaim", False)
    if reclaim:
        session_obj = session_manager.reclaim_session(tab_id, sid, user_id)
        if session_obj:
            logger.info(f"Reattached to session: {tab_id} (sid: {sid})")
            # Send current scrollback buffer to the new client
            if session_obj.buffer:
                full_buffer = "".join(session_obj.buffer)
                full_buffer = full_buffer.replace("\x1b[3J", "").replace("\x1b[2J", "")
                chunk_size = 1024 * 64
                lines = full_buffer.split("\n")
                current_chunk = []
                current_size = 0

                for i, line in enumerate(lines):
                    suffix = "\n" if i < len(lines) - 1 else ""
                    line_with_suffix = line + suffix
                    line_len = len(line_with_suffix)

                    if current_size + line_len > chunk_size and current_chunk:
                        socketio.emit(
                            "pty-output",
                            {"output": "".join(current_chunk)},
                            room=sid,
                        )
                        socketio.sleep(0.01)
                        current_chunk = []
                        current_size = 0

                    current_chunk.append(line_with_suffix)
                    current_size += line_len

                if current_chunk:
                    socketio.emit(
                        "pty-output",
                        {"output": "".join(current_chunk)},
                        room=sid,
                    )
                    socketio.sleep(0.01)

            try:
                set_winsize(session_obj.fd, data.get("rows", 24), data.get("cols", 80))
            except Exception as e:
                logger.warning(f"Failed to set winsize on fd {session_obj.fd}: {e}")
            return
        else:
            logger.warning(
                f"Reclaim failed for session {tab_id}. Creating a fresh session."
            )
            socketio.emit(
                "pty-output",
                {
                    "output": "\r\n\x1b[2m[Session not found on server. Starting fresh...]\x1b[0m\r\n"
                },
                room=sid,
            )

    old_session = session_manager.remove_session(tab_id, user_id)
    if old_session:
        logger.info(f"Killing old session {tab_id} for fresh restart")
        kill_and_reap(old_session.pid)

    resume = data.get("resume", True)
    if isinstance(resume, str):
        if resume.lower() == "true":
            resume = True
        elif resume.lower() == "false":
            resume = False

    cols = data.get("cols", 80)
    rows = data.get("rows", 24)
    ssh_target = data.get("ssh_target")
    ssh_dir = data.get("ssh_dir")

    import sys

    sys.stderr.write(f"HOSTS: {get_config().get('HOSTS', [])}\n")
    sys.stderr.flush()
    env_vars = {}
    for host in get_config().get("HOSTS", []):
        if ssh_target and host.get("target") == ssh_target:
            env_vars = host.get("env_vars") or {}
            break
        elif not ssh_target and (
            host.get("target") == "local"
            or host.get("label", "").lower() == "local"
            or not host.get("target")
        ):
            env_vars = host.get("env_vars") or {}
            break

    logger.info(f"ENV_VARS resolved to: {env_vars}")

    if is_fake:
        env_vars["GEMINI_WEBUI_HARNESS_ID"] = tab_id
        ssh_target = None
        gemini_bin_override = GEMINI_BIN
    else:
        gemini_bin_override = GEMINI_BIN
        if env_config.BYPASS_AUTH_FOR_TESTING:
            env_vars["GEMINI_WEBUI_HARNESS_ID"] = tab_id

    _, _, ssh_dir_path = get_config_paths()

    cmd = build_terminal_command(
        ssh_target,
        ssh_dir,
        resume,
        ssh_dir_path,
        gemini_bin_override,
        env_vars=env_vars,
        is_fake=is_fake,
        executable_override=executable_override,
    )

    if not cmd:
        socketio.emit(
            "pty-output",
            {"output": "\r\n\x1b[31mError: Invalid SSH target format\x1b[0m\r\n"},
            room=sid,
        )
        return

    (child_pid, fd) = pty.fork()
    if child_pid == 0:
        try:
            os.setsid()
        except OSError:
            pass
        os.closerange(3, 65536)
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["FORCE_COLOR"] = "3"

        if env_vars:
            for k, v in env_vars.items():
                if k == "PATH":
                    env["PATH"] = f"{v}:{env.get('PATH', '')}"
                else:
                    env[k] = str(v)

        if is_fake or env_config.BYPASS_AUTH_FOR_TESTING:
            env["GEMINI_WEBUI_HARNESS_ID"] = tab_id

        try:
            os.execvpe(cmd[0], cmd, env)
        except OSError as e:
            import sys

            msg = f"\r\n\x1b[1;31mError: Failed to execute '{cmd[0]}' on the server.\x1b[0m\r\n\x1b[1;31mDetails: {e}\x1b[0m\r\n\x1b[1;33mPlease ensure '{cmd[0]}' is installed and accessible in the system PATH.\x1b[0m\r\n"
            os.write(sys.stdout.fileno(), msg.encode())
            os._exit(1)
        os._exit(0)
    else:
        import fcntl

        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        add_managed_pty(child_pid)
        session_obj = Session(
            tab_id,
            fd,
            child_pid,
            user_id,
            title=data.get("title") or "",
            ssh_target=ssh_target,
            ssh_dir=ssh_dir,
            resume=resume,
        )
        session_manager.add_session(session_obj, on_remove=kill_and_reap)
        session_manager.reclaim_session(tab_id, sid, user_id)

        # Broadcast sync to ensure client has the new session
        if user_id:
            if session_manager.persistence:
                persisted = session_manager.persistence.load()
                user_persisted = {
                    tid: s
                    for tid, s in persisted.items()
                    if s.get("user_id") == user_id
                }
                socketio.emit("sync-tabs", user_persisted, room=f"user_{user_id}")

        # Start the dedicated output reader for this session
        socketio.start_background_task(session_output_reader, tab_id)

        _, _, ssh_dir_path = get_config_paths()
        app_config = {"SSH_DIR": ssh_dir_path}
        threading.Thread(
            target=session_manager.update_file_cache,
            args=(tab_id, app_config),
            daemon=True,
        ).start()

        try:
            set_winsize(fd, rows, cols)
        except Exception as e:
            logger.warning(f"Failed to set winsize on fd {fd}: {e}")

        initial_msg = (
            "\x1b[2mEstablishing connection...\x1b[0m\r\n"
            if ssh_target
            else "\x1b[2mLoading Context...\x1b[0m\r\n"
        )
        socketio.emit("pty-output", {"output": initial_msg}, room=tab_id)


@socketio.on("get_management_sessions")
def handle_get_management_sessions(*args):
    if not env_config.BYPASS_AUTH_FOR_TESTING and not session.get("authenticated"):
        return {"error": "unauthenticated"}
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )

    active = session_manager.list_sessions(user_id)
    if not session_manager.persistence:
        return active

    persisted = session_manager.persistence.load()
    # Merge: Persisted sessions that are not currently active should be added
    # with an 'inactive' or 'orphaned' state for the UI to show they can be resumed.
    active_ids = {s["tab_id"] for s in active}

    for tid, s in persisted.items():
        if s.get("user_id") == user_id and tid not in active_ids:
            # Add as inactive session
            active.append(
                {
                    "tab_id": tid,
                    "title": s["title"],
                    "ssh_target": s["ssh_target"],
                    "ssh_dir": s["ssh_dir"],
                    "resume": s["resume"],
                    "last_active": 0,
                    "is_orphaned": True,
                    "is_inactive": True,
                }
            )

    return active


@socketio.on("get_sessions")
def handle_get_sessions(data):
    if not env_config.BYPASS_AUTH_FOR_TESTING and not session.get("authenticated"):
        return {"error": "unauthenticated"}

    ssh_target = data.get("ssh_target")
    ssh_dir = data.get("ssh_dir")
    cache_key = (
        f"{'ssh' if ssh_target else 'local'}:{ssh_target or 'local'}:{ssh_dir or ''}"
    )
    use_cache = data.get("cache") is True
    bg = data.get("bg") is True

    from src.routes.terminal import _get_gemini_sessions_impl

    return _get_gemini_sessions_impl(ssh_target, ssh_dir, cache_key, use_cache, bg)
