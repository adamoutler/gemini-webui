import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import env_config
except ImportError:
    from src.config import env_config
if not env_config.SKIP_MONKEY_PATCH:
    import eventlet

    eventlet.monkey_patch()

import pty
import select
import signal
import subprocess
import struct
import time
import fcntl
import termios
import re
import logging
import json
import shutil
import shlex
import socket
import datetime
import threading
import uuid
import tempfile
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    Response,
    session,
    jsonify,
    send_from_directory,
    redirect,
    send_file,
)
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from auth_ldap import check_auth
    from session_manager import Session, SessionManager
    from process_manager import (
        validate_ssh_target,
        fetch_sessions_for_host,
        build_terminal_command,
        get_remote_command_prefix,
    )
    from share_manager import ShareManager
    from utils import smart_file_search
except ImportError:
    from src.auth_ldap import check_auth
    from src.session_manager import Session, SessionManager
    from src.process_manager import (
        validate_ssh_target,
        fetch_sessions_for_host,
        build_terminal_command,
        get_remote_command_prefix,
    )
    from src.share_manager import ShareManager
    from src.utils import smart_file_search

# Global config holder and defaults
config = {}
GEMINI_BIN = env_config.GEMINI_BIN
ADMIN_USER = env_config.ADMIN_USER
ADMIN_PASS = env_config.ADMIN_PASS
LDAP_SERVER = env_config.LDAP_SERVER
LDAP_BASE_DN = env_config.LDAP_BASE_DN
LDAP_BIND_USER_DN = env_config.LDAP_BIND_USER_DN
LDAP_BIND_PASS = env_config.LDAP_BIND_PASS
LDAP_AUTHORIZED_GROUP = env_config.LDAP_AUTHORIZED_GROUP
LDAP_FALLBACK_DOMAIN = env_config.LDAP_FALLBACK_DOMAIN

# SECURITY PARADIGM: Fail-Closed Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
app = Flask(__name__, template_folder=template_dir)
csrf = CSRFProtect(app)


@app.errorhandler(CSRFError)
def csrf_error(e):
    return jsonify(
        {"error": "CSRF token missing or incorrect", "csrf_expired": True}
    ), 400


try:
    with open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"
        ),
        "r",
    ) as f:
        APP_VERSION = f.read().strip()
except Exception as e:
    logger.warning(f"Failed to read VERSION: {e}")
    APP_VERSION = "unknown"


@app.context_processor
def inject_version():
    return dict(version=APP_VERSION)


# Handle proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
)

session_manager = SessionManager()
share_manager = ShareManager()

# Background session cache: key -> {"output": str, "error": str, "timestamp": float}
session_results_cache = {}
session_results_cache_lock = threading.Lock()

ephemeral_sessions = {}
active_fake_sockets = {}
active_fake_sockets_lock = threading.Lock()

# Precompile terminal ID regex for performance
IDENTIFICATION_REGEX = re.compile(r"\x1b\[\??\d+(?:;\d+)*c")


def cleanup_orphaned_ptys():
    """Cleanup orphaned sessions based on ORPHANED_SESSION_TTL."""
    is_testing = app.config.get("TESTING") or env_config.BYPASS_AUTH_FOR_TESTING
    while True:
        try:
            ttl = app.config.get("ORPHANED_SESSION_TTL", 3600)
            now = time.time()
            for session in session_manager.get_all_sessions():
                if (
                    session.orphaned_at is not None
                    and (now - session.orphaned_at) > ttl
                ):
                    try:
                        os.kill(session.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    try:
                        os.waitpid(session.pid, os.WNOHANG)
                    except OSError:
                        pass
                    session_manager.remove_session(session.tab_id)
        except Exception as e:
            logger.error(f"Error in cleanup_orphaned_ptys: {e}")

        if is_testing:
            break
        socketio.sleep(60)


def get_config_paths():
    data_dir = app.config.get("DATA_DIR", env_config.DATA_DIR)

    # Check if data_dir is writable
    data_writable = os.access(
        data_dir if os.path.exists(data_dir) else os.path.dirname(data_dir.rstrip("/")),
        os.W_OK,
    )

    if not data_writable:
        # Fallback to /tmp
        if os.access("/tmp", os.W_OK):
            data_dir = "/tmp/gemini-data"
            os.makedirs(data_dir, exist_ok=True)
        else:
            # Absolute last resort: nothing is writable. Use /data but expect failures.
            logger.warning(
                "CRITICAL: No writable storage found (/data and /tmp are RO). Functionality will be limited."
            )

    config_file = os.path.join(data_dir, "config.json")
    ssh_dir = os.path.join(data_dir, ".ssh")
    return data_dir, config_file, ssh_dir


def get_config():
    data_dir, config_file, ssh_dir = get_config_paths()
    conf = {
        "LDAP_SERVER": LDAP_SERVER,
        "LDAP_BASE_DN": LDAP_BASE_DN,
        "LDAP_BIND_USER_DN": LDAP_BIND_USER_DN,
        "LDAP_BIND_PASS": LDAP_BIND_PASS,
        "LDAP_AUTHORIZED_GROUP": LDAP_AUTHORIZED_GROUP,
        "LDAP_FALLBACK_DOMAIN": LDAP_FALLBACK_DOMAIN,
        "ALLOWED_ORIGINS": env_config.ALLOWED_ORIGINS,
        "DATA_WRITABLE": os.access(os.path.dirname(config_file), os.W_OK),
        "TMP_WRITABLE": os.access("/tmp", os.W_OK),
        "HOSTS": [{"label": "local", "type": "local"}],
    }

    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                file_config = json.load(f)
                conf.update(file_config)
        except Exception as e:
            logger.error(f"Error loading config file: {e}")

    return conf


def init_app():
    global \
        config, \
        ADMIN_USER, \
        ADMIN_PASS, \
        LDAP_SERVER, \
        LDAP_BASE_DN, \
        LDAP_BIND_USER_DN, \
        LDAP_BIND_PASS, \
        LDAP_AUTHORIZED_GROUP, \
        LDAP_FALLBACK_DOMAIN
    data_dir, config_file, ssh_dir = get_config_paths()
    logger.info(f"Initializing app with DATA_DIR: {data_dir}")

    if not getattr(app, "_blueprints_registered", False):
        register_blueprints(app)
        app._blueprints_registered = True

    # Try FS operations but don't crash if they fail (RO filesystem)
    try:
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        gemini_data = os.path.join(data_dir, ".gemini")
        os.makedirs(gemini_data, mode=0o700, exist_ok=True)

        # Fix permissions if volume mount made them root-owned
        for path in [gemini_data, ssh_dir]:
            try:
                stat = os.stat(path)
                if stat.st_uid == 0:
                    shutil.chown(path, user="node", group="node")
                    # Recursively fix if it was existing root data
                    for root, dirs, files in os.walk(path):
                        for d in dirs:
                            shutil.chown(
                                os.path.join(root, d), user="node", group="node"
                            )
                        for f in files:
                            shutil.chown(
                                os.path.join(root, f), user="node", group="node"
                            )
            except Exception as e:
                logger.warning(f"Failed to fix permissions on {path}: {e}")

        # Generate instance SSH key if not exists
        key_path = os.path.join(ssh_dir, "id_ed25519")
        if not os.path.exists(key_path):
            try:
                hostname = socket.gethostname()
                datestr = datetime.datetime.now().strftime("%Y%m%d")
                comment = f"gemini-webui-{hostname}-{datestr}"
                logger.info(
                    f"Generating new instance SSH key with comment: {comment}..."
                )
                subprocess.run(
                    [
                        "ssh-keygen",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        key_path,
                        "-C",
                        comment,
                    ],
                    check=True,
                )
                shutil.chown(key_path, user="node", group="node")
                shutil.chown(key_path + ".pub", user="node", group="node")
                os.chmod(key_path, 0o600)
            except Exception as e:
                logger.warning(f"Failed to generate SSH key: {e}")
    except Exception as e:
        logger.warning(
            f"FS initialization partially failed (likely RO filesystem): {e}"
        )

    # Manage symlink /home/node/.gemini -> [current gemini_data]
    home_gemini = "/home/node/.gemini"
    gemini_data = os.path.join(data_dir, ".gemini")
    try:
        if os.path.islink(home_gemini):
            if os.readlink(home_gemini) != gemini_data:
                os.unlink(home_gemini)
                os.symlink(gemini_data, home_gemini)
        elif not os.path.exists(home_gemini):
            os.makedirs(os.path.dirname(home_gemini), exist_ok=True)
            os.symlink(gemini_data, home_gemini)
    except Exception as e:
        logger.warning(f"Failed to manage symlink for {home_gemini}: {e}")

    config = get_config()
    ADMIN_USER = config.get("ADMIN_USER", ADMIN_USER)
    ADMIN_PASS = config.get("ADMIN_PASS", ADMIN_PASS)
    LDAP_SERVER = config.get("LDAP_SERVER")
    LDAP_BASE_DN = config.get("LDAP_BASE_DN")
    LDAP_BIND_USER_DN = config.get("LDAP_BIND_USER_DN")
    LDAP_BIND_PASS = config.get("LDAP_BIND_PASS")
    LDAP_AUTHORIZED_GROUP = config.get("LDAP_AUTHORIZED_GROUP")
    LDAP_FALLBACK_DOMAIN = config.get("LDAP_FALLBACK_DOMAIN")

    # Load secret key from config (env) or generate one
    import secrets

    fallback_key = secrets.token_hex(32)
    secret_key = config.get("SECRET_KEY") or env_config.SECRET_KEY or fallback_key

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE="Lax",
        DATA_DIR=data_dir,
        WTF_CSRF_ENABLED=not app.config.get("TESTING", False),
    )
    return config


# SECURITY PARADIGM: Secure Headers (CSP, HSTS, etc.)
csp = {
    "default-src": "'self'",
    "script-src": [
        "'self'",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://unpkg.com",
        "'unsafe-inline'",
        "'unsafe-eval'",
    ],
    "style-src": ["'self'", "https://cdn.jsdelivr.net", "'unsafe-inline'"],
    "connect-src": [
        "'self'",
        "ws:",
        "wss:",
        "http:",
        "https:",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
    ],
    "manifest-src": ["'self'"],
}

Talisman(
    app,
    content_security_policy=csp,
    force_https=False,  # Proxy handles HTTPS
    strict_transport_security=True,
    session_cookie_secure=False,
)  # Set to True if proxy handles SSL

# Only allow origins from environment or localhost
if env_config.BYPASS_AUTH_FOR_TESTING:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
else:
    # Default to '*' for ease of use if not specified, but log it
    allowed_origins_raw = env_config.ALLOWED_ORIGINS_RAW
    if allowed_origins_raw:
        allowed_origins = allowed_origins_raw.split(",")
    else:
        logger.warning(
            "ALLOWED_ORIGINS not set. Defaulting to '*' (CORS restricted disabled)."
        )
        allowed_origins = "*"
    socketio = SocketIO(
        app, cors_allowed_origins=allowed_origins, async_mode="eventlet"
    )


def authenticate():
    return Response(
        "Login Required", 401, {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )


def authenticated_only(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        bypass = env_config.BYPASS_AUTH_FOR_TESTING
        is_auth = session.get("authenticated")
        if bypass or is_auth:
            return f(*args, **kwargs)
        return authenticate()

    return wrapped


@socketio.on("connect")
def handle_connect(auth=None):
    from flask_wtf.csrf import validate_csrf, ValidationError

    auth = auth or {}
    csrf_token = auth.get("csrf_token")
    logger.info(f"Socket.io connect attempt with token: {csrf_token}")

    try:
        if app.config.get("WTF_CSRF_ENABLED", True):
            validate_csrf(csrf_token)
            app.logger.debug("CSRF validation passed")
        else:
            logger.info("CSRF validation disabled via config")
    except ValidationError as e:
        logger.warning(f"CSRF validation failed: {e}")
        raise ConnectionRefusedError("invalid_csrf")

    if env_config.BYPASS_AUTH_FOR_TESTING:
        return True

    if not session.get("authenticated"):
        return False
    return True


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    tab_id = session_manager.sid_to_tabid.pop(sid, None)

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


@app.before_request
def require_auth():
    if (
        env_config.BYPASS_AUTH_FOR_TESTING
        or app.config.get("BYPASS_AUTH_FOR_TESTING") == "true"
    ):
        session["authenticated"] = True
        return

    if request.path in [
        "/health",
        "/api/health",
        "/favicon.ico",
        "/favicon.svg",
        "/manifest.json",
        "/sw.js",
    ] or request.path.startswith("/s/"):
        return

    auth = request.authorization

    # EXCLUSIVE AUTHENTICATION:
    # If LDAP is configured, it is the ONLY allowed method.
    if LDAP_SERVER:
        if auth and check_auth(
            auth.username,
            auth.password,
            LDAP_SERVER,
            LDAP_BASE_DN,
            LDAP_BIND_USER_DN,
            LDAP_BIND_PASS,
            LDAP_AUTHORIZED_GROUP,
            LDAP_FALLBACK_DOMAIN,
        ):
            session["authenticated"] = True
            session["user_id"] = auth.username
            return
    else:
        # Fall back to local admin credentials ONLY if LDAP is not configured.
        if auth and auth.username == ADMIN_USER and auth.password == ADMIN_PASS:
            session["authenticated"] = True
            session["user_id"] = ADMIN_USER
            return

    if not session.get("authenticated"):
        return authenticate()


def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception as e:
        logger.error(f"Failed to set winsize on fd {fd}: {e}")


def read_and_forward_pty_output():
    max_read_bytes = 1024 * 20
    while True:
        if app.config.get("TESTING") and not session_manager.sessions:
            socketio.sleep(0.1)
            if not session_manager.sessions:
                break
        socketio.sleep(0.01)
        for tab_id, session in list(session_manager.sessions.items()):
            fd = session.fd
            decoder = session.decoder
            sid = session_manager.tabid_to_sid.get(tab_id)
            try:
                batched_output = []
                for _ in range(10):  # Read up to 200KB per tick
                    (data_ready, _, _) = select.select([fd], [], [], 0)
                    if data_ready:
                        output = os.read(fd, max_read_bytes)
                        if output:
                            batched_output.append(output)
                        else:
                            # Flush before raising EOFError
                            break_eof = True
                            break
                    else:
                        break

                if batched_output:
                    combined_output = b"".join(batched_output)
                    decoded_output = decoder.decode(combined_output)
                    if decoded_output:
                        if "\x1b[" in decoded_output and "c" in decoded_output:
                            filtered_output = IDENTIFICATION_REGEX.sub(
                                "", decoded_output
                            )
                        else:
                            filtered_output = decoded_output
                        if filtered_output:
                            try:
                                with open(
                                    f"/tmp/session-{tab_id}-DEBUG.log",
                                    "a",
                                    encoding="utf-8",
                                ) as debug_log:
                                    debug_log.write(filtered_output)
                            except Exception as e:
                                logger.error(f"Failed to write to debug log: {e}")
                            session.append_buffer(filtered_output)
                            if sid:
                                socketio.emit(
                                    "pty-output", {"output": filtered_output}, room=sid
                                )

                if "break_eof" in locals() and break_eof:
                    raise EOFError("EOF reached")
            except (OSError, IOError, EOFError):
                logger.info(f"Removing session {tab_id} due to I/O error")
                old_session = session_manager.remove_session(tab_id)
                ephemeral_sessions.pop(tab_id, None)
                if old_session and old_session.pid is not None:
                    try:
                        # Process might already be dead, but we must reap it to prevent zombies
                        os.kill(old_session.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    try:
                        os.waitpid(old_session.pid, 0)
                    except OSError:
                        pass


def background_session_preloader():
    """Warms the session cache on startup."""
    run_once = False
    while True:
        if app.config.get("TESTING") and run_once:
            break
        run_once = True
        try:
            hosts = get_config().get("HOSTS", [])
            for host in hosts:
                key = f"{host.get('type')}:{host.get('target', 'local')}:{host.get('dir', '')}"
                logger.info(f"Background preloading sessions for: {host.get('label')}")
                _, _, ssh_dir_path = get_config_paths()
                res = fetch_sessions_for_host(host, ssh_dir_path, GEMINI_BIN)
                with session_results_cache_lock:
                    session_results_cache[key] = res
        except Exception as e:
            logger.error(f"Preloader error: {e}")
        # Only run once at startup, then sleep for a long time or until manually triggered
        # For simplicity, we just do it once then sleep for an hour.
        socketio.sleep(3600)


@socketio.on("update_title")
def update_title(data):
    sid = request.sid
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    tab_id = data.get("tab_id") or session_manager.sid_to_tabid.get(sid)
    title = data.get("title")
    if tab_id and title:
        session_manager.update_title(tab_id, title, user_id)


@socketio.on("pty-input")
def pty_input(data):
    sid = request.sid
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    tab_id = session_manager.sid_to_tabid.get(sid)
    session_obj = session_manager.get_session(tab_id, user_id)
    if session_obj:
        session_obj.last_seen = time.time()
        # Filter out terminal identification responses (DA) to prevent loops
        # e.g. \x1b[?1;2c or similar. These often get echoed back on reclaim.
        input_data = data.get("input", "")
        if not input_data:
            return
        if input_data.startswith("\x1b[?") and input_data.endswith("c"):
            return
        os.write(session_obj.fd, input_data.encode())


@socketio.on("resize")
def pty_resize(data):
    sid = request.sid
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
    sid = data.get("sid") or getattr(request, "sid", None)
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    tab_id = data.get("tab_id")
    mode = data.get("mode")

    if mode == "fake":
        # For ephemeral sessions, the UUID is passed in the 'resume' field
        ephemeral_id = data.get("resume")
        if ephemeral_id in ephemeral_sessions:
            tab_id = ephemeral_id

    if not tab_id:
        return

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
        executable_base = session_info.get("executable", "python3 src/fake_gemini.py")
        scenario = session_info.get("args", "default")
        executable_override = f"{executable_base} --scenario {shlex.quote(scenario)}"

    reclaim = data.get("reclaim", False)
    if reclaim:

        def handle_steal(t_id, old_sid):
            logger.info(f"Stealing session {t_id} from SID {old_sid} for new SID {sid}")
            socketio.emit("session-stolen", {"tab_id": t_id}, room=old_sid)

        session_obj = session_manager.reclaim_session(
            tab_id, sid, user_id, on_steal=handle_steal
        )
        if session_obj:
            logger.info(f"Reattached to session: {tab_id} (sid: {sid})")
            if session_obj.buffer:
                full_buffer = "".join(session_obj.buffer)
                chunk_size = 1024 * 64
                for i in range(0, len(full_buffer), chunk_size):
                    socketio.emit(
                        "pty-output",
                        {"output": full_buffer[i : i + chunk_size]},
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

    if len(session_manager.sessions) >= 10 and tab_id not in session_manager.sessions:
        oldest_session = None
        oldest_time = time.time()

        for s in session_manager.sessions.values():
            if s.last_seen < oldest_time:
                oldest_time = s.last_seen
                oldest_session = s

        if oldest_session:
            logger.debug(
                f"LRU Eviction: Dropping session {oldest_session.tab_id} (last seen {oldest_time}) to make room."
            )
            sid_to_notify = session_manager.tabid_to_sid.get(oldest_session.tab_id)
            if sid_to_notify:
                socketio.emit(
                    "pty-output",
                    {
                        "output": "\r\n\x1b[2m[Warning: This session was evicted to make room for a new one.]\x1b[0m\r\n"
                    },
                    room=sid_to_notify,
                )

            session_manager.remove_session(oldest_session.tab_id)
            try:
                os.kill(oldest_session.pid, signal.SIGKILL)
            except Exception:
                pass
            try:
                os.waitpid(oldest_session.pid, 0)
            except Exception:
                pass

    old_session = session_manager.remove_session(tab_id, user_id)
    if old_session:
        logger.info(f"Killing old session {tab_id} for fresh restart")
        try:
            os.kill(old_session.pid, signal.SIGKILL)
        except Exception:
            pass
        try:
            os.waitpid(old_session.pid, 0)
        except Exception:
            pass
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

    env_vars = {}
    if ssh_target:
        for host in get_config().get("HOSTS", []):
            if host.get("target") == ssh_target:
                env_vars = host.get("env_vars") or {}
                break

    if is_fake:
        os.environ["GEMINI_WEBUI_HARNESS_ID"] = tab_id
        env_vars["GEMINI_WEBUI_HARNESS_ID"] = tab_id
        ssh_target = None
        gemini_bin_override = GEMINI_BIN  # not used if executable_override is set
    else:
        gemini_bin_override = GEMINI_BIN

    (child_pid, fd) = pty.fork()
    if child_pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.environ["COLORTERM"] = "truecolor"
        os.environ["FORCE_COLOR"] = "3"

        if is_fake:
            os.environ["GEMINI_WEBUI_HARNESS_ID"] = tab_id

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
            print("\r\nInvalid SSH target format\r\n")
            os._exit(1)

        os.execvp(cmd[0], cmd)
        os._exit(0)
    else:
        # Parent process: create a new session
        session_obj = Session(
            tab_id,
            fd,
            child_pid,
            user_id,
            ssh_target=ssh_target,
            ssh_dir=ssh_dir,
            resume=resume,
        )
        session_manager.add_session(session_obj)

        _, _, ssh_dir_path = get_config_paths()
        app_config = {"SSH_DIR": ssh_dir_path}
        threading.Thread(
            target=session_manager.update_file_cache,
            args=(tab_id, app_config),
            daemon=True,
        ).start()

        def handle_steal(t_id, old_sid):
            logger.info(f"Stealing session {t_id} from SID {old_sid} for new SID {sid}")
            socketio.emit("session-stolen", {"tab_id": t_id}, room=old_sid)

        session_manager.reclaim_session(
            tab_id, sid, user_id, on_steal=handle_steal
        )  # Connect current SID

        try:
            set_winsize(fd, rows, cols)
        except Exception as e:
            logger.warning(f"Failed to set winsize on fd {fd}: {e}")
        socketio.emit(
            "pty-output", {"output": "\x1b[2mLoading Context...\x1b[0m\r\n"}, room=sid
        )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/test-launcher")
def test_launcher():
    return render_template("test_launcher.html")


@app.route("/fake_session_init")
def fake_session_init():
    scenario = request.args.get("scenario", "default")
    session_id = str(uuid.uuid4())
    ephemeral_sessions[session_id] = {
        "executable": "python3 src/fake_gemini.py",
        "args": scenario,
        "used": False,
    }
    return redirect(f"/?session_id={session_id}&mode=fake")


@app.route("/favicon.ico")
@app.route("/favicon.svg")
def favicon():
    return app.send_static_file("favicon.svg")


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")


@app.route("/sw.js")
def service_worker():
    response = app.send_static_file("sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.route("/api/management/sessions", methods=["GET"])
@authenticated_only
def list_active_sessions():
    """List all active/orphaned sessions managed by the backend for current user."""
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    return jsonify(session_manager.list_sessions(user_id))


@socketio.on("get_management_sessions")
def handle_get_management_sessions(*args):
    if not env_config.BYPASS_AUTH_FOR_TESTING and not session.get("authenticated"):
        return {"error": "unauthenticated"}
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    return session_manager.list_sessions(user_id)


@app.route("/api/management/sessions/<tab_id>", methods=["DELETE"])
@authenticated_only
def terminate_managed_session(tab_id):
    """Terminate a backend managed session and kill its process."""
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )

    if not tab_id:
        return jsonify({"error": "Tab ID required"}), 400
    session_obj = session_manager.remove_session(tab_id, user_id)
    if session_obj:
        logger.info(f"Terminating managed session {tab_id}")
        ephemeral_sessions.pop(tab_id, None)
        try:
            os.kill(session_obj.pid, signal.SIGKILL)
        except Exception:
            pass
        try:
            os.waitpid(session_obj.pid, 0)
        except Exception:
            pass

        return jsonify({"status": "success"})

    return jsonify({"error": "Session not found"}), 404


@app.route("/api/sessions/<session_id>/search_files", methods=["GET"])
@authenticated_only
def search_files(session_id):
    q = request.args.get("q", "")
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )

    session_obj = session_manager.get_session(session_id, user_id)
    if not session_obj:
        return jsonify({"error": "Session not found"}), 404

    matches = smart_file_search(session_obj.file_cache, q)
    return jsonify({"matches": matches})


@app.route("/api/sessions", methods=["GET"])
@authenticated_only
def list_gemini_sessions():
    ssh_target = request.args.get("ssh_target")
    ssh_dir = request.args.get("ssh_dir")
    cache_key = (
        f"{'ssh' if ssh_target else 'local'}:{ssh_target or 'local'}:{ssh_dir or ''}"
    )

    # Check if we should update or use cache
    use_cache = request.args.get("cache") == "true"
    bg = request.args.get("bg") == "true"

    res = _get_gemini_sessions_impl(ssh_target, ssh_dir, cache_key, use_cache, bg)
    if (
        isinstance(res, dict)
        and isinstance(res.get("error"), str)
        and "timeout" in res["error"].lower()
    ):
        return jsonify(res), 504
    return jsonify(res)


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

    return _get_gemini_sessions_impl(ssh_target, ssh_dir, cache_key, use_cache, bg)


def _get_gemini_sessions_impl(ssh_target, ssh_dir, cache_key, use_cache, bg):
    if use_cache:
        with session_results_cache_lock:
            if cache_key in session_results_cache:
                return session_results_cache[cache_key]

    if bg:
        with session_results_cache_lock:
            if not hasattr(list_gemini_sessions, "fetching_locks"):
                list_gemini_sessions.fetching_locks = set()
            should_fetch = cache_key not in list_gemini_sessions.fetching_locks
            if should_fetch:
                list_gemini_sessions.fetching_locks.add(cache_key)

        if should_fetch:

            def background_fetch(target, directory, key):
                try:
                    _, _, ssh_dir_path = get_config_paths()
                    res = fetch_sessions_for_host(
                        {
                            "target": target,
                            "dir": directory,
                            "type": "ssh" if target else "local",
                        },
                        ssh_dir_path,
                        GEMINI_BIN,
                    )
                    with session_results_cache_lock:
                        session_results_cache[key] = res
                except Exception as e:
                    logger.error(f"Background fetch error: {e}")
                    with session_results_cache_lock:
                        session_results_cache[key] = {"error": str(e)}
                finally:
                    with session_results_cache_lock:
                        if key in list_gemini_sessions.fetching_locks:
                            list_gemini_sessions.fetching_locks.remove(key)

            socketio.start_background_task(
                background_fetch, ssh_target, ssh_dir, cache_key
            )

        return {"status": "fetching"}

    _, _, ssh_dir_path = get_config_paths()
    result = fetch_sessions_for_host(
        {
            "target": ssh_target,
            "dir": ssh_dir,
            "type": "ssh" if ssh_target else "local",
        },
        ssh_dir_path,
        GEMINI_BIN,
    )

    with session_results_cache_lock:
        session_results_cache[cache_key] = result

    return result


@app.route("/api/sessions/terminate", methods=["POST"])
@authenticated_only
def terminate_remote_session():
    data = request.json
    ssh_target = data.get("ssh_target")
    ssh_dir = data.get("ssh_dir")
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "Session ID required"}), 400

    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return jsonify({"error": "Invalid SSH target"}), 400

        remote_prefix = get_remote_command_prefix(ssh_dir, GEMINI_BIN)
        remote_cmd = f"{remote_prefix} if command -v {GEMINI_BIN} >/dev/null 2>&1; then {GEMINI_BIN} --terminate {shlex.quote(str(session_id))}; fi"
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"

        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
        _, _, ssh_dir_path = get_config_paths()
        known_hosts_path = os.path.join(ssh_dir_path, "known_hosts")
        cmd.extend(["-o", f"UserKnownHostsFile={known_hosts_path}"])
        if os.path.exists(ssh_dir_path):
            for f in os.listdir(ssh_dir_path):
                if (
                    os.path.isfile(os.path.join(ssh_dir_path, f))
                    and f not in ["config", "known_hosts"]
                    and not f.endswith(".pub")
                ):
                    cmd.extend(["-i", os.path.join(ssh_dir_path, f)])
        cmd.extend(["--", ssh_target, login_wrapped_cmd])
    else:
        cmd = [GEMINI_BIN, "--terminate", str(session_id)]

    try:
        subprocess.run(cmd)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["GET"])
@authenticated_only
def get_current_config():
    conf = get_config()
    conf.pop("LDAP_BIND_PASS", None)
    conf.pop("ADMIN_PASS", None)
    return jsonify(conf)


@app.route("/api/config", methods=["POST"])
@authenticated_only
def update_config():
    new_conf = request.json
    curr_conf = get_config()
    curr_conf.update(new_conf)
    _, config_file, _ = get_config_paths()
    with open(config_file, "w") as f:
        json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})


@app.route("/api/settings/export", methods=["GET"])
@authenticated_only
def export_settings():
    try:
        data_dir, _, _ = get_config_paths()
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, "settings")
        # create a zip file
        shutil.make_archive(zip_path, "zip", data_dir)
        return send_file(
            zip_path + ".zip",
            as_attachment=True,
            download_name="settings.gwui",
            mimetype="application/zip",
        )
    except Exception as e:
        logger.error(f"Failed to export settings: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/csrf", methods=["GET"])
def get_csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


@app.route("/api/upload", methods=["POST"])
@authenticated_only
def upload_file():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No selected file"}), 400

    # preserve path structure if provided, otherwise fallback to standard secure_filename
    original_filename = file.filename
    if "/" in original_filename or "\\" in original_filename:
        # replace backslashes and normalize
        normalized_path = original_filename.replace("\\", "/")
        # extract directories and secure each part
        parts = [secure_filename(p) for p in normalized_path.split("/") if p]
        filename = "/".join(parts)
    else:
        filename = secure_filename(file.filename)

    if not filename:
        return jsonify({"status": "error", "message": "Invalid filename"}), 400

    workspace_dir = os.path.join(env_config.DATA_DIR, "workspace")

    # Ensure save path is within workspace
    base_path = os.path.abspath(workspace_dir)
    save_path = os.path.abspath(os.path.join(base_path, filename))
    if not save_path.startswith(base_path):
        return jsonify({"status": "error", "message": "Access denied"}), 403

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)

    ssh_target = request.form.get("ssh_target")
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return jsonify({"status": "error", "message": "Invalid SSH target"}), 400

        ssh_dir = request.form.get("ssh_dir")
        _, _, ssh_dir_path = get_config_paths()

        # Build base SSH arguments
        base_ssh_args = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
        known_hosts_path = os.path.join(ssh_dir_path, "known_hosts")
        base_ssh_args.extend(["-o", f"UserKnownHostsFile={known_hosts_path}"])
        if os.path.exists(ssh_dir_path):
            for f in os.listdir(ssh_dir_path):
                if (
                    os.path.isfile(os.path.join(ssh_dir_path, f))
                    and f not in ["config", "known_hosts"]
                    and not f.endswith(".pub")
                ):
                    base_ssh_args.extend(["-i", os.path.join(ssh_dir_path, f)])

        # Determine remote path
        if not ssh_dir or ssh_dir == "~":
            remote_path = filename
        elif ssh_dir.startswith("~/"):
            remote_path = f"{ssh_dir[2:]}/{filename}"
        else:
            remote_path = os.path.join(ssh_dir, filename).replace("\\", "/")

        # Ensure directory structure exists on remote
        remote_dir = os.path.dirname(remote_path)

        # Extract port if present in ssh_target
        port = None
        clean_target = ssh_target
        if ":" in ssh_target:
            parts = ssh_target.rsplit(":", 1)
            if parts[1].isdigit():
                clean_target = parts[0]
                port = parts[1]

        ssh_cmd_base = ["ssh"] + base_ssh_args
        if port:
            ssh_cmd_base.extend(["-p", port])

        scp_cmd_base = ["scp"] + base_ssh_args
        if port:
            scp_cmd_base.extend(["-P", port])

        if remote_dir:
            ssh_cmd = ssh_cmd_base + [
                "--",
                clean_target,
                f"mkdir -p {shlex.quote(remote_dir)}",
            ]
            res = subprocess.run(ssh_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                return jsonify(
                    {
                        "status": "error",
                        "message": f"Failed to create remote directory: {res.stderr}",
                    }
                ), 500

        # Run SCP
        scp_cmd = scp_cmd_base + ["--", save_path, f"{clean_target}:{remote_path}"]
        try:
            result = subprocess.run(scp_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return jsonify(
                    {"status": "error", "message": f"SCP failed: {result.stderr}"}
                ), 500

            verify_cmd = ssh_cmd_base + [
                "--",
                clean_target,
                f"ls {shlex.quote(remote_path)}",
            ]
            verify_res = subprocess.run(verify_cmd, capture_output=True)
            if verify_res.returncode != 0:
                return jsonify(
                    {
                        "status": "error",
                        "message": "SCP returned 0, but file verification failed on remote host.",
                    }
                ), 500

            path_cmd = ssh_cmd_base + [
                "--",
                clean_target,
                f"realpath {shlex.quote(remote_path)} 2>/dev/null || readlink -m {shlex.quote(remote_path)} 2>/dev/null || echo {shlex.quote(remote_path)}",
            ]
            path_res = subprocess.run(path_cmd, capture_output=True, text=True)
            if path_res.returncode == 0 and path_res.stdout.strip():
                filename = path_res.stdout.strip()

        except Exception as e:
            return jsonify({"status": "error", "message": f"SCP error: {str(e)}"}), 500

    return jsonify({"status": "success", "filename": filename})


@app.route("/api/download/<path:filename>", methods=["GET"])
@authenticated_only
def download_file(filename):
    workspace_dir = os.path.join(env_config.DATA_DIR, "workspace")

    # Securely resolve the path and prevent directory traversal
    try:
        # We need to securely join the filename to the workspace_dir
        base_path = os.path.abspath(workspace_dir)
        target_path = os.path.abspath(os.path.join(base_path, filename))

        # Verify the target_path starts with the base_path
        if not target_path.startswith(base_path):
            return jsonify({"status": "error", "message": "Access denied"}), 403

        if not os.path.isfile(target_path):
            return jsonify(
                {"status": "error", "message": f"File not found: {target_path}"}
            ), 404

        # Get the directory and the actual filename to send
        dir_name = os.path.dirname(target_path)
        base_name = os.path.basename(target_path)

        print(f"DEBUG: sending {base_name} from {dir_name}")
        return send_from_directory(dir_name, base_name, as_attachment=True)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/s/<share_id>", methods=["GET"])
def view_share(share_id):
    if not re.match(r"^[a-zA-Z0-9-]+$", share_id):
        return "Invalid share ID", 400

    metadata = share_manager.get_share_metadata(share_id)
    if not metadata:
        return "Share not found", 404

    file_path = metadata.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return "Share data not found", 404

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        logger.error(f"Failed to read share {share_id}: {e}")
        return "Error reading share data", 500

    return render_template(
        "share.html",
        session_name=metadata.get("session_name", "Unknown"),
        theme=metadata.get("theme", "dark"),
        html_content=html_content,
    )


@app.route("/api/shares/create", methods=["POST"])
@authenticated_only
def create_share():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload"}), 400

    session_name = data.get("session_name")
    html_content = data.get("html_content")
    theme = data.get("theme", "dark")

    if not session_name or not html_content:
        return jsonify({"error": "Missing session_name or html_content"}), 400

    try:
        share_id = share_manager.create_share(html_content, session_name, theme)
        return jsonify({"share_id": share_id, "share_url": f"/s/{share_id}"})
    except Exception as e:
        logger.error(f"Error creating share: {e}")
        return jsonify({"error": "Failed to create share"}), 500


@app.route("/api/shares", methods=["GET"])
@authenticated_only
def list_shares():
    try:
        shares = share_manager.list_shares()
        return jsonify(shares)
    except Exception as e:
        logger.error(f"Error listing shares: {e}")
        return jsonify({"error": "Failed to list shares"}), 500


@app.route("/api/shares/<share_id>", methods=["DELETE"])
@authenticated_only
def delete_share(share_id):
    if not re.match(r"^[a-zA-Z0-9-]+$", share_id):
        return jsonify({"error": "Invalid share ID"}), 400

    try:
        success = share_manager.delete_share(share_id)
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Share not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting share: {e}")
        return jsonify({"error": "Failed to delete share"}), 500


@app.route("/health")
def health_check_root():
    return jsonify({"status": "ok"})


@app.route("/api/health")
def health_check():
    return jsonify({"status": "ok"})


def register_blueprints(app_instance):
    from src.host_key_routes import host_key_bp

    app_instance.register_blueprint(host_key_bp)


if __name__ == "__main__":
    init_app()
    if not app.config.get("TESTING"):
        socketio.start_background_task(read_and_forward_pty_output)
        socketio.start_background_task(cleanup_orphaned_ptys)
        if not env_config.SKIP_PRELOADER:
            socketio.start_background_task(background_session_preloader)

    debug_mode = env_config.FLASK_DEBUG
    use_reloader = env_config.FLASK_USE_RELOADER
    socketio.run(
        app,
        host="0.0.0.0",
        port=env_config.PORT,
        debug=debug_mode,
        use_reloader=use_reloader,
    )
