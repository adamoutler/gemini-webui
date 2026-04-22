import os
import sys
import eventlet
import eventlet.debug

# Perform monkey patching as early as possible
if os.environ.get("SKIP_MONKEY_PATCH") != "true":
    eventlet.monkey_patch()
    eventlet.debug.hub_prevent_multiple_readers(False)

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
    current_app,
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
from flask_socketio import ConnectionRefusedError, join_room
from src.extensions import socketio
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_smorest import Api

try:
    from auth_ldap import check_auth
    from services.session_store import Session, SessionManager, session_manager
    from services.process_engine import (
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
    from src.services.session_store import Session, SessionManager, session_manager
    from src.services.process_engine import (
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
from src.shared_state import (
    ephemeral_sessions,
    session_results_cache,
    session_results_cache_lock,
    abandoned_pids,
    abandoned_pids_lock,
    active_fake_sockets,
    active_fake_sockets_lock,
)


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
            # Use config TTL if available, otherwise fallback to 2s in testing or 3600s in production
            ttl = app.config.get("ORPHANED_SESSION_TTL")
            if ttl is None:
                ttl = 2 if is_testing else 3600
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
        socketio.sleep(1 if is_testing else 60)
        if is_testing and os.environ.get("GEMWEBUI_HARNESS") != "1":
            break


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
    import src.gateways.terminal_socket

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

    from src.bootstrap import setup_environment

    setup_environment(data_dir, ssh_dir)

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
if getattr(socketio, "server", None) is None:
    if env_config.BYPASS_AUTH_FOR_TESTING:
        socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")
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
        socketio.init_app(
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


import src.gateways.terminal_socket


@app.before_request
def require_auth():
    if (
        env_config.BYPASS_AUTH_FOR_TESTING
        or current_app.config.get("BYPASS_AUTH_FOR_TESTING") == "true"
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
        from src.gateways.terminal_socket import background_session_preloader

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
                socketio.start_background_task(
                    src.gateways.terminal_socket.background_session_preloader
                )

    debug_mode = env_config.FLASK_DEBUG
    use_reloader = env_config.FLASK_USE_RELOADER
    socketio.run(
        app,
        host="0.0.0.0",
        port=env_config.PORT,
        debug=debug_mode,
        use_reloader=use_reloader,
    )
