import os
import sys
import eventlet

# Perform monkey patching as early as possible
if os.environ.get("SKIP_MONKEY_PATCH") != "true":
    eventlet.monkey_patch()

import errno

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import env_config
except ImportError:
    from src.config import env_config
import threading

abandoned_pids = set()
abandoned_pids_lock = threading.Lock()

if not env_config.SKIP_MONKEY_PATCH:
    # Manually patch subprocess.run to handle GreenletExit and prevent zombie processes
    import subprocess
    import eventlet.green.subprocess

    def safe_subprocess_run(*popenargs, **kwargs):
        timeout = kwargs.pop("timeout", None)
        input_data = kwargs.pop("input", None)
        check = kwargs.pop("check", False)
        if kwargs.pop("capture_output", False):
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE

        with eventlet.green.subprocess.Popen(*popenargs, **kwargs) as process:
            try:
                text_mode = kwargs.get("text", False)
                if input_data and process.stdin:
                    if text_mode and isinstance(input_data, str):
                        process.stdin.write(input_data)
                    elif not text_mode and isinstance(input_data, bytes):
                        process.stdin.write(input_data)
                    process.stdin.close()

                if timeout is not None:
                    import time

                    start_time = time.time()
                    while process.poll() is None:
                        if time.time() - start_time > timeout:
                            process.kill()
                            raise eventlet.green.subprocess.TimeoutExpired(
                                process.args, timeout
                            )
                        eventlet.sleep(0.01)

                stdout = process.stdout.read() if process.stdout else None
                stderr = process.stderr.read() if process.stderr else None
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
            except BaseException:
                try:
                    process.kill()
                except OSError:
                    pass
                with abandoned_pids_lock:
                    abandoned_pids.add(process.pid)
                raise

    subprocess.run = safe_subprocess_run
    eventlet.green.subprocess.run = safe_subprocess_run

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
from flask_socketio import SocketIO, ConnectionRefusedError, join_room
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_smorest import Api

try:
    from auth_ldap import check_auth
    from session_manager import Session, SessionManager, session_manager
    from process_manager import (
        validate_ssh_target,
        fetch_sessions_for_host,
        build_terminal_command,
        get_remote_command_prefix,
        build_ssh_args,
    )
    from share_manager import ShareManager
    from utils import smart_file_search
except ImportError:
    from src.auth_ldap import check_auth
    from src.session_manager import Session, SessionManager, session_manager
    from src.process_manager import (
        validate_ssh_target,
        fetch_sessions_for_host,
        build_terminal_command,
        get_remote_command_prefix,
        build_ssh_args,
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

share_manager = ShareManager()

# Background session cache: key -> {"output": str, "error": str, "timestamp": float}
session_results_cache = {}
session_results_cache_lock = threading.Lock()

from src.shared_state import ephemeral_sessions

active_fake_sockets = {}
active_fake_sockets_lock = threading.Lock()

# Precompile terminal ID regex for performance
IDENTIFICATION_REGEX = re.compile(r"\x1b\[\??\d+(?:;\d+)*c")


managed_ptys = set()
managed_ptys_lock = threading.Lock()


def add_managed_pty(pid):
    if pid is not None:
        with managed_ptys_lock:
            managed_ptys.add(pid)


def zombie_reaper_task():
    """Periodically reaps any managed PTY processes that have exited to prevent zombies."""
    while True:
        try:
            with managed_ptys_lock:
                to_remove = set()
                for pid in list(managed_ptys):
                    try:
                        # Reap ONLY this specific PID to avoid stealing reaps from other subprocess calls
                        res = os.waitpid(pid, os.WNOHANG)
                        wpid = res[0] if isinstance(res, tuple) else res
                        if wpid == pid:
                            to_remove.add(pid)
                    except ChildProcessError:
                        to_remove.add(pid)
                    except OSError:
                        pass
                managed_ptys.difference_update(to_remove)

            with abandoned_pids_lock:
                to_remove = set()
                for pid in list(abandoned_pids):
                    try:
                        res = os.waitpid(pid, os.WNOHANG)
                        wpid = res[0] if isinstance(res, tuple) else res
                        if wpid == pid:
                            to_remove.add(pid)
                    except ChildProcessError:
                        to_remove.add(pid)
                    except OSError:
                        pass
                abandoned_pids.difference_update(to_remove)
        except Exception as e:
            logger.error(f"Error in zombie reaper: {e}")
        socketio.sleep(2)


def kill_and_reap(pid):
    """Kills a process and its entire group, then reaps the zombie immediately."""
    if pid is None:
        return
    try:
        # Kill the entire process group started by setsid() in child
        os.killpg(os.getpgid(pid), signal.SIGKILL)
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
                    kill_and_reap(session.pid)
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
    import hashlib
    import socket

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

    if not conf.get("host_id"):
        hostname = socket.gethostname()
        h_id = hashlib.sha512(hostname.encode()).hexdigest()[:4]
        conf["host_id"] = h_id
        # Persist if writable
        if conf.get("DATA_WRITABLE"):
            try:
                with open(config_file, "w") as f:
                    json.dump(conf, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to persist host_id: {e}")

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
        LDAP_FALLBACK_DOMAIN, \
        share_manager
    data_dir, config_file, ssh_dir = get_config_paths()
    logger.info(f"Initializing app with DATA_DIR: {data_dir}")

    # Initialize ShareManager with the determined data_dir
    share_manager = ShareManager(data_dir=data_dir)

    if not getattr(app, "_blueprints_registered", False):
        register_blueprints(app)
        app._blueprints_registered = True

    # Try FS operations but don't crash if they fail (RO filesystem)
    try:
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        gemini_data = os.path.join(data_dir, ".gemini")
        os.makedirs(gemini_data, mode=0o700, exist_ok=True)

        # Fix permissions if volume mount made them root-owned
        current_uid = os.getuid()
        for path in [gemini_data, ssh_dir]:
            try:
                stat = os.stat(path)
                if stat.st_uid == 0:
                    try:
                        # Attempt to use the current user/group instead of hardcoded 'node'
                        shutil.chown(path, user=current_uid, group=os.getgid())
                        # Recursively fix if it was existing root data
                        for root, dirs, files in os.walk(path):
                            for d in dirs:
                                shutil.chown(
                                    os.path.join(root, d),
                                    user=current_uid,
                                    group=os.getgid(),
                                )
                            for f in files:
                                shutil.chown(
                                    os.path.join(root, f),
                                    user=current_uid,
                                    group=os.getgid(),
                                )
                    except (LookupError, PermissionError):
                        pass
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
                try:
                    shutil.chown(key_path, user=current_uid, group=os.getgid())
                    shutil.chown(key_path + ".pub", user=current_uid, group=os.getgid())
                except (LookupError, PermissionError):
                    pass
                os.chmod(key_path, 0o600)
            except Exception as e:
                logger.warning(f"Failed to generate SSH key: {e}")
    except Exception as e:
        logger.warning(
            f"FS initialization partially failed (likely RO filesystem): {e}"
        )

    # Manage symlink in home directory if it exists and is writable
    try:
        home_dir = os.path.expanduser("~")
        if os.path.exists(home_dir) and os.access(home_dir, os.W_OK):
            home_gemini = os.path.join(home_dir, ".gemini")
            gemini_data = os.path.join(data_dir, ".gemini")
            if os.path.islink(home_gemini):
                if os.readlink(home_gemini) != gemini_data:
                    os.unlink(home_gemini)
                    os.symlink(gemini_data, home_gemini)
            elif not os.path.exists(home_gemini):
                os.symlink(gemini_data, home_gemini)
    except Exception as e:
        logger.warning(f"Failed to manage symlink for .gemini: {e}")

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

    secret_key = config.get("SECRET_KEY") or env_config.SECRET_KEY
    if not secret_key:
        secret_key = secrets.token_hex(32)
        # Persist the generated fallback key if writable
        if config.get("DATA_WRITABLE"):
            try:
                config["SECRET_KEY"] = secret_key
                with open(config_file, "w") as f:
                    json.dump(config, f, indent=4)
                logger.info("Generated and persisted new fallback SECRET_KEY")
            except Exception as e:
                logger.error(f"Failed to persist fallback SECRET_KEY: {e}")
        else:
            logger.warning(
                "SECRET_KEY not found and storage not writable. Sessions will invalidate on restart."
            )

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
    ],
    "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
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
    from flask import request as socket_request

    sid = getattr(socket_request, "sid", None)
    from flask_wtf.csrf import validate_csrf, ValidationError

    auth = auth or {}
    csrf_token = auth.get("csrf_token")

    try:
        if app.config.get("WTF_CSRF_ENABLED", True):
            validate_csrf(csrf_token)
            app.logger.debug("CSRF validation passed")
        else:
            logger.info("CSRF validation disabled via config")
    except ValidationError as e:
        app.logger.debug(f"CSRF validation failed (expected during token refresh): {e}")
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


@app.before_request
def require_auth():
    if (
        env_config.BYPASS_AUTH_FOR_TESTING
        or app.config.get("BYPASS_AUTH_FOR_TESTING") == "true"
    ):
        session["authenticated"] = True
        return

    if (
        request.path
        in [
            "/health",
            "/api/health",
            "/favicon.ico",
            "/favicon.svg",
            "/manifest.json",
            "/sw.js",
        ]
        or request.path.startswith("/s/")
        or request.path.startswith("/api/v1/")
    ):
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
            socketio.emit("session-terminated", {"tab_id": tab_id}, room=tab_id)


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
    if tab_id and title:
        session_manager.update_title(tab_id, title, user_id)


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

    env_vars = {}
    if ssh_target:
        for host in get_config().get("HOSTS", []):
            if host.get("target") == ssh_target:
                env_vars = host.get("env_vars") or {}
                break

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

        if is_fake or env_config.BYPASS_AUTH_FOR_TESTING:
            env["GEMINI_WEBUI_HARNESS_ID"] = tab_id

        os.execvpe(cmd[0], cmd, env)
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

        if resume == "new":

            def discover_session_id(t_id, s_target, s_dir, s_id):
                import re
                from src.process_manager import fetch_sessions_for_host

                max_attempts = 10
                for attempt in range(max_attempts):
                    socketio.sleep(1.5)
                    try:
                        _, _, ssh_dir_path = get_config_paths()
                        res = fetch_sessions_for_host(
                            {
                                "target": s_target,
                                "dir": s_dir,
                                "type": "ssh" if s_target else "local",
                            },
                            ssh_dir_path,
                            GEMINI_BIN,
                        )
                        output = res.get("output", "")
                        sessions = []
                        for line in output.split("\n"):
                            match = re.search(
                                r"^\s*(\d+)\.\s+(.*?)\s+\((.*?)\)\s+\[(.*?)\]", line
                            )
                            if match:
                                sessions.append(
                                    {
                                        "id": match.group(1),
                                        "name": match.group(2),
                                        "uuid": match.group(4),
                                    }
                                )

                        found_id = None
                        for s in sessions:
                            if s.get("uuid") == t_id or s.get("name") == t_id:
                                found_id = s["id"]
                                break

                        if not found_id and sessions:
                            try:
                                found_id = max(int(s["id"]) for s in sessions)
                            except (ValueError, TypeError):
                                pass

                        if found_id:
                            logger.info(
                                f"Discovered session ID {found_id} for tab {t_id}"
                            )
                            socketio.emit(
                                "session_assigned",
                                {"tab_id": t_id, "session_id": found_id},
                                to=sid,
                            )
                            return
                    except Exception as e:
                        logger.error(f"Error in session discovery: {e}")

                logger.warning(f"Failed to discover session ID for tab {t_id}")

            socketio.start_background_task(
                discover_session_id, tab_id, ssh_target, ssh_dir, sid
            )


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


def register_blueprints(app_instance):
    from src.routes.host_keys import host_key_bp
    from src.routes.ui import ui_bp
    from src.routes.api import api_bp
    from src.routes.terminal import terminal_bp
    from src.routes.shares import shares_bp

    app_instance.register_blueprint(host_key_bp)
    app_instance.register_blueprint(ui_bp)
    app_instance.register_blueprint(api_bp)
    app_instance.register_blueprint(terminal_bp)
    app_instance.register_blueprint(shares_bp)


if __name__ == "__main__":
    init_app()
    if not app.config.get("TESTING"):
        # When using Flask's reloader, this block is executed twice:
        # once by the reloader process and once by the worker process.
        # We only want to start background tasks in the worker process.
        if (
            os.environ.get("WERKZEUG_RUN_MAIN") == "true"
            or not env_config.FLASK_USE_RELOADER
        ):
            socketio.start_background_task(cleanup_orphaned_ptys)
            socketio.start_background_task(zombie_reaper_task)
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
