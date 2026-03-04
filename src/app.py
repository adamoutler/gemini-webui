import os
if os.environ.get('SKIP_MONKEY_PATCH') != 'true':
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
from functools import wraps
from flask import Flask, render_template, request, Response, session, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
try:
    from auth_ldap import check_auth
    from session_manager import Session, SessionManager
    from process_manager import validate_ssh_target, fetch_sessions_for_host, build_terminal_command, get_remote_command_prefix
except ImportError:
    from src.auth_ldap import check_auth
    from src.session_manager import Session, SessionManager
    from src.process_manager import validate_ssh_target, fetch_sessions_for_host, build_terminal_command, get_remote_command_prefix

# Global config holder and defaults
config = {}
GEMINI_BIN = os.environ.get('GEMINI_BIN', 'gemini')
ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'admin')
LDAP_SERVER = os.environ.get('LDAP_SERVER')
LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN')
LDAP_BIND_USER_DN = os.environ.get('LDAP_BIND_USER_DN')
LDAP_BIND_PASS = os.environ.get('LDAP_BIND_PASS')
LDAP_AUTHORIZED_GROUP = os.environ.get('LDAP_AUTHORIZED_GROUP')
LDAP_FALLBACK_DOMAIN = os.environ.get('LDAP_FALLBACK_DOMAIN', 'example.com')

# SECURITY PARADIGM: Fail-Closed Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)
csrf = CSRFProtect(app)

try:
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'VERSION'), 'r') as f:
        APP_VERSION = f.read().strip()
except Exception:
    APP_VERSION = "unknown"

@app.context_processor
def inject_version():
    return dict(version=APP_VERSION)

# Handle proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

session_manager = SessionManager()

# Background session cache: key -> {"output": str, "error": str, "timestamp": float}
session_results_cache = {}

# Precompile terminal ID regex for performance
IDENTIFICATION_REGEX = re.compile(r'\x1b\[\??\d+(?:;\d+)*c')

def cleanup_orphaned_ptys():
    """Cleanup orphaned sessions based on ORPHANED_SESSION_TTL."""
    is_testing = app.config.get('TESTING') or os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true'
    while True:
        try:
            ttl = app.config.get('ORPHANED_SESSION_TTL', 3600)
            now = time.time()
            for session in session_manager.get_all_sessions():
                if session.orphaned_at is not None and (now - session.orphaned_at) > ttl:
                    try:
                        os.kill(session.pid, signal.SIGKILL)
                        os.waitpid(session.pid, os.WNOHANG)
                    except OSError:
                        pass
                    session_manager.remove_session(session.tab_id)
        except Exception as e:
            logger.error(f"Error in cleanup_orphaned_ptys: {e}")
            
        if is_testing: break
        socketio.sleep(60)

def get_config_paths():
    data_dir = app.config.get('DATA_DIR', os.environ.get('DATA_DIR', "/data"))
    
    # Check if data_dir is writable
    data_writable = os.access(data_dir if os.path.exists(data_dir) else os.path.dirname(data_dir.rstrip('/')), os.W_OK)
    
    if not data_writable:
        # Fallback to /tmp
        if os.access("/tmp", os.W_OK):
            data_dir = "/tmp/gemini-data"
            os.makedirs(data_dir, exist_ok=True)
        else:
            # Absolute last resort: nothing is writable. Use /data but expect failures.
            logger.warning("CRITICAL: No writable storage found (/data and /tmp are RO). Functionality will be limited.")
        
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
        "ALLOWED_ORIGINS": os.environ.get('ALLOWED_ORIGINS', '*'),
        "DATA_WRITABLE": os.access(os.path.dirname(config_file), os.W_OK),
        "TMP_WRITABLE": os.access("/tmp", os.W_OK),
        "HOSTS": [
            { "label": 'local', "type": 'local' }
        ]
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                conf.update(file_config)
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            
    return conf

def init_app():
    global config, ADMIN_USER, ADMIN_PASS, LDAP_SERVER, LDAP_BASE_DN, LDAP_BIND_USER_DN, LDAP_BIND_PASS, LDAP_AUTHORIZED_GROUP, LDAP_FALLBACK_DOMAIN
    data_dir, config_file, ssh_dir = get_config_paths()
    logger.info(f"Initializing app with DATA_DIR: {data_dir}")
    
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
                    shutil.chown(path, user='node', group='node')
                    # Recursively fix if it was existing root data
                    for root, dirs, files in os.walk(path):
                        for d in dirs: shutil.chown(os.path.join(root, d), user='node', group='node')
                        for f in files: shutil.chown(os.path.join(root, f), user='node', group='node')
            except Exception: pass
        
        # Generate instance SSH key if not exists
        key_path = os.path.join(ssh_dir, 'id_ed25519')
        if not os.path.exists(key_path):
            try:
                hostname = socket.gethostname()
                datestr = datetime.datetime.now().strftime('%Y%m%d')
                comment = f"gemini-webui-{hostname}-{datestr}"
                logger.info(f"Generating new instance SSH key with comment: {comment}...")
                subprocess.run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', key_path, '-C', comment], check=True)
                shutil.chown(key_path, user='node', group='node')
                shutil.chown(key_path + '.pub', user='node', group='node')
                os.chmod(key_path, 0o600)
            except Exception: pass
    except Exception as e:
        logger.warning(f"FS initialization partially failed (likely RO filesystem): {e}")

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
    except Exception: pass
    
    config = get_config()
    ADMIN_USER = config.get('ADMIN_USER', ADMIN_USER)
    ADMIN_PASS = config.get('ADMIN_PASS', ADMIN_PASS)
    LDAP_SERVER = config.get('LDAP_SERVER')
    LDAP_BASE_DN = config.get('LDAP_BASE_DN')
    LDAP_BIND_USER_DN = config.get('LDAP_BIND_USER_DN')
    LDAP_BIND_PASS = config.get('LDAP_BIND_PASS')
    LDAP_AUTHORIZED_GROUP = config.get('LDAP_AUTHORIZED_GROUP')
    LDAP_FALLBACK_DOMAIN = config.get('LDAP_FALLBACK_DOMAIN')

    # Load secret key from config (env) or generate one
    import secrets
    fallback_key = secrets.token_hex(32)
    secret_key = config.get('SECRET_KEY') or os.environ.get('SECRET_KEY') or fallback_key

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False, 
        SESSION_COOKIE_SAMESITE='Lax',
        DATA_DIR=data_dir,
        WTF_CSRF_ENABLED=not app.config.get('TESTING', False)
    )
    return config

# SECURITY PARADIGM: Secure Headers (CSP, HSTS, etc.)
csp = {
    'default-src': "'self'",
    'script-src': [
        "'self'",
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com',
        'https://unpkg.com',
        "'unsafe-inline'",
        "'unsafe-eval'"
    ],
    'style-src': [
        "'self'",
        'https://cdn.jsdelivr.net',
        "'unsafe-inline'"
    ],
    'connect-src': [
        "'self'", 
        'ws:', 
        'wss:',
        'http:',
        'https:',
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com'
    ],
    'manifest-src': ["'self'"]
}

Talisman(app, 
         content_security_policy=csp, 
         force_https=False, # Proxy handles HTTPS
         strict_transport_security=True,
         session_cookie_secure=False) # Set to True if proxy handles SSL

# Only allow origins from environment or localhost
if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true':
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
else:
    # Default to '*' for ease of use if not specified, but log it
    allowed_origins_raw = os.environ.get('ALLOWED_ORIGINS')
    if allowed_origins_raw:
        allowed_origins = allowed_origins_raw.split(',')
    else:
        logger.warning("ALLOWED_ORIGINS not set. Defaulting to '*' (CORS restricted disabled).")
        allowed_origins = "*"
    socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='eventlet')

def authenticate():
    return Response(
    'Login Required', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def authenticated_only(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        bypass = os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true'
        is_auth = session.get('authenticated')
        if bypass or is_auth:
            return f(*args, **kwargs)
        return authenticate()
    return wrapped

@socketio.on('connect')
def handle_connect():
    if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true':
        return True
    if not session.get('authenticated'):
        return False
    return True

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    tab_id = session_manager.sid_to_tabid.pop(sid, None)
    if tab_id:
        session_manager.orphan_session(tab_id)
        logger.info(f"Session {tab_id} orphaned on disconnect (sid: {sid})")

@app.before_request
def require_auth():
    if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true' or app.config.get('BYPASS_AUTH_FOR_TESTING') == 'true':
        session['authenticated'] = True
        return
        
    if request.path in ['/health', '/api/health', '/favicon.ico', '/favicon.svg', '/manifest.json', '/sw.js']:
        return

    auth = request.authorization
    
    # EXCLUSIVE AUTHENTICATION: 
    # If LDAP is configured, it is the ONLY allowed method.
    if LDAP_SERVER:
        if auth and check_auth(auth.username, auth.password, LDAP_SERVER, LDAP_BASE_DN, LDAP_BIND_USER_DN, LDAP_BIND_PASS, LDAP_AUTHORIZED_GROUP, LDAP_FALLBACK_DOMAIN):
            session['authenticated'] = True
            session['user_id'] = auth.username
            return
    else:
        # Fall back to local admin credentials ONLY if LDAP is not configured.
        if auth and auth.username == ADMIN_USER and auth.password == ADMIN_PASS:
            session['authenticated'] = True
            session['user_id'] = ADMIN_USER
            return

    if not session.get('authenticated'):
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
        if app.config.get('TESTING') and not session_manager.sessions:
            socketio.sleep(0.1)
            if not session_manager.sessions: break
        socketio.sleep(0.01)
        for tab_id, session in list(session_manager.sessions.items()):
            fd = session.fd
            decoder = session.decoder
            sid = session_manager.tabid_to_sid.get(tab_id)
            try:
                batched_output = []
                for _ in range(10): # Read up to 200KB per tick
                    (data_ready, _, _) = select.select([fd], [], [], 0)
                    if data_ready:
                        output = os.read(fd, max_read_bytes)
                        if output:
                            batched_output.append(output)
                        else:
                            break
                    else:
                        break
                
                if batched_output:
                    combined_output = b"".join(batched_output)
                    decoded_output = decoder.decode(combined_output)
                    if decoded_output:
                        # Filter out terminal identification responses (e.g. \x1b[?62;c or \x1b[0c)
                        # These are often triggered by the terminal on reclaim and shouldn't be buffered.
                        if '\x1b[' in decoded_output and 'c' in decoded_output:
                            filtered_output = IDENTIFICATION_REGEX.sub('', decoded_output)
                        else:
                            filtered_output = decoded_output
                        if filtered_output:
                            session.append_buffer(filtered_output)
                            if sid:
                                socketio.emit('pty-output', {'output': filtered_output}, room=sid)
            except (OSError, IOError, EOFError):
                logger.info(f"Removing session {tab_id} due to I/O error")
                session_manager.remove_session(tab_id)


def background_session_preloader():
    """Warms the session cache on startup."""
    run_once = False
    while True:
        if app.config.get('TESTING') and run_once:
            break
        run_once = True
        try:
            hosts = get_config().get('HOSTS', [])
            for host in hosts:
                key = f"{host.get('type')}:{host.get('target', 'local')}:{host.get('dir', '')}"
                logger.info(f"Background preloading sessions for: {host.get('label')}")
                _, _, ssh_dir_path = get_config_paths()
                session_results_cache[key] = fetch_sessions_for_host(host, ssh_dir_path, GEMINI_BIN)
        except Exception as e:
            logger.error(f"Preloader error: {e}")
        # Only run once at startup, then sleep for a long time or until manually triggered
        # For simplicity, we just do it once then sleep for an hour.
        socketio.sleep(3600)

@socketio.on('pty-input')
def pty_input(data):
    sid = request.sid
    user_id = session.get('user_id') or ('admin' if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true' else None)
    tab_id = session_manager.sid_to_tabid.get(sid)
    session_obj = session_manager.get_session(tab_id, user_id)
    if session_obj:
        session_obj.last_seen = time.time()
        # Filter out terminal identification responses (DA) to prevent loops
        # e.g. \x1b[?1;2c or similar. These often get echoed back on reclaim.
        input_data = data['input']
        if input_data.startswith('\x1b[?') and input_data.endswith('c'):
            return
        os.write(session_obj.fd, input_data.encode())

@socketio.on('resize')
def pty_resize(data):
    sid = request.sid
    user_id = session.get('user_id') or ('admin' if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true' else None)
    tab_id = session_manager.sid_to_tabid.get(sid)
    session_obj = session_manager.get_session(tab_id, user_id)
    if session_obj:
        try:
            set_winsize(session_obj.fd, data['rows'], data['cols'])
        except Exception:
            pass

@socketio.on('restart')
def pty_restart(data):
    sid = data.get('sid') or getattr(request, 'sid', None)
    user_id = session.get('user_id') or ('admin' if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true' else None)
    tab_id = data.get('tab_id')
    if not tab_id:
        return
    
    reclaim = data.get('reclaim', False)
    if reclaim:
        def handle_steal(t_id, old_sid):
            logger.info(f"Stealing session {t_id} from SID {old_sid} for new SID {sid}")
            socketio.emit('session-stolen', {'tab_id': t_id}, room=old_sid)

        session_obj = session_manager.reclaim_session(tab_id, sid, user_id, on_steal=handle_steal)
        if session_obj:
            logger.info(f"Reattached to session: {tab_id} (sid: {sid})")
            # Flush the scrollback buffer to the new client in chunks
            if session_obj.buffer:
                full_buffer = "".join(session_obj.buffer)
                chunk_size = 1024 * 64 # 64KB
                for i in range(0, len(full_buffer), chunk_size):
                    socketio.emit('pty-output', {'output': full_buffer[i:i+chunk_size]}, room=sid)
                    socketio.sleep(0.01)
            
            # Re-sync terminal size
            try:
                set_winsize(session_obj.fd, data.get('rows', 24), data.get('cols', 80))
            except Exception: pass
            return
        else:
            logger.warning(f"Reclaim failed for session {tab_id}. Creating a fresh session.")
            socketio.emit('pty-output', {'output': '\r\n\x1b[2m[Session not found on server. Starting fresh...]\x1b[0m\r\n'}, room=sid)

    # LRU EVICTION POLICY: Limit to 10 total active sessions
    if len(session_manager.sessions) >= 10 and tab_id not in session_manager.sessions:
        # Find the least recently used session
        oldest_session = None
        oldest_time = time.time()
        
        for s in session_manager.sessions.values():
            if s.last_seen < oldest_time:
                oldest_time = s.last_seen
                oldest_session = s
        
        if oldest_session:
            logger.info(f"LRU Eviction: Dropping session {oldest_session.tab_id} (last seen {oldest_time}) to make room.")
            
            # Inform the client that their session was evicted if they are still connected
            sid_to_notify = session_manager.tabid_to_sid.get(oldest_session.tab_id)
            if sid_to_notify:
                socketio.emit('pty-output', {'output': '\r\n\x1b[2m[Warning: This session was evicted to make room for a new one.]\x1b[0m\r\n'}, room=sid_to_notify)

            session_manager.remove_session(oldest_session.tab_id)
            try:
                os.kill(oldest_session.pid, signal.SIGKILL)
                os.waitpid(oldest_session.pid, 0)
            except Exception: pass
    
    # Explicit restart or session not found: Clean up old one first
    old_session = session_manager.remove_session(tab_id, user_id)
    if old_session:
        logger.info(f"Killing old session {tab_id} for fresh restart")
        try:
            os.kill(old_session.pid, signal.SIGKILL)
            os.waitpid(old_session.pid, 0)
        except Exception: pass
            
    resume = data.get('resume', True)
    if isinstance(resume, str):
        if resume.lower() == 'true':
            resume = True
        elif resume.lower() == 'false':
            resume = False
            
    cols = data.get('cols', 80)
    rows = data.get('rows', 24)
    ssh_target = data.get('ssh_target')
    ssh_dir = data.get('ssh_dir')
    
    (child_pid, fd) = pty.fork()
    if child_pid == 0:
        os.environ['TERM'] = 'xterm-256color'
        os.environ['COLORTERM'] = 'truecolor'
        os.environ['FORCE_COLOR'] = '3'
        
        _, _, ssh_dir_path = get_config_paths()
        cmd = build_terminal_command(ssh_target, ssh_dir, resume, ssh_dir_path, GEMINI_BIN)
        
        if not cmd:
            print("\r\nInvalid SSH target format\r\n")
            os._exit(1)
            
        os.execvp(cmd[0], cmd)
        os._exit(0)
    else:
        # Parent process: create a new session
        session_obj = Session(tab_id, fd, child_pid, user_id, ssh_target=ssh_target, ssh_dir=ssh_dir, resume=resume)
        session_manager.add_session(session_obj)
        
        def handle_steal(t_id, old_sid):
            logger.info(f"Stealing session {t_id} from SID {old_sid} for new SID {sid}")
            socketio.emit('session-stolen', {'tab_id': t_id}, room=old_sid)
            
        session_manager.reclaim_session(tab_id, sid, user_id, on_steal=handle_steal) # Connect current SID
        
        try: set_winsize(fd, rows, cols)
        except Exception: pass
        socketio.emit('pty-output', {'output': '\x1b[2mLoading Context...\x1b[0m\r\n'}, room=sid)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
@app.route('/favicon.svg')
def favicon():
    return app.send_static_file('favicon.svg')

@app.route('/manifest.json')
def manifest():
    return app.send_static_file('manifest.json')

@app.route('/sw.js')
def service_worker():
    response = app.send_static_file('sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/api/hosts', methods=['GET'])
@authenticated_only
def list_hosts():
    return jsonify(get_config().get('HOSTS', []))

@app.route('/api/management/sessions', methods=['GET'])
@authenticated_only
def list_active_sessions():
    """List all active/orphaned sessions managed by the backend for current user."""
    user_id = session.get('user_id') or ('admin' if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true' else None)
    return jsonify(session_manager.list_sessions(user_id))

@app.route('/api/management/sessions/terminate', methods=['POST'])
@authenticated_only
def terminate_managed_session():
    """Terminate a backend managed session and kill its process."""
    data = request.json
    tab_id = data.get('tab_id')
    user_id = session.get('user_id') or ('admin' if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true' else None)
    
    if not tab_id:
        return jsonify({"error": "Tab ID required"}), 400
        
    session_obj = session_manager.remove_session(tab_id, user_id)
    if session_obj:
        logger.info(f"Terminating managed session {tab_id}")
        try:
            os.kill(session_obj.pid, signal.SIGKILL)
            os.waitpid(session_obj.pid, 0)
        except Exception as e:
            logger.error(f"Error killing process {session_obj.pid}: {e}")
            
        return jsonify({"status": "success"})
    
    return jsonify({"error": "Session not found"}), 404

@app.route('/api/sessions', methods=['GET'])
@authenticated_only
def list_gemini_sessions():
    ssh_target = request.args.get('ssh_target')
    ssh_dir = request.args.get('ssh_dir')
    cache_key = f"{'ssh' if ssh_target else 'local'}:{ssh_target or 'local'}:{ssh_dir or ''}"
    
    # Check if we should update or use cache
    use_cache = request.args.get('cache') == 'true'
    if use_cache and cache_key in session_results_cache:
        return jsonify(session_results_cache[cache_key])
    
    _, _, ssh_dir_path = get_config_paths()
    result = fetch_sessions_for_host({'target': ssh_target, 'dir': ssh_dir, 'type': 'ssh' if ssh_target else 'local'}, ssh_dir_path, GEMINI_BIN)
    err = result.get('error')
    if err and 'timeout' in err.lower():
        return jsonify(result), 504
    session_results_cache[cache_key] = result
    return jsonify(result)

@app.route('/api/hosts', methods=['POST'])
@authenticated_only
def add_host():
    new_host = request.json
    label = new_host.get('label')
    old_label = new_host.get('old_label')
    if not label:
        return jsonify({"status": "error", "message": "Label is required"}), 400
        
    curr_conf = get_config()
    hosts = curr_conf.get('HOSTS', [])
    
    # Check if we are updating an existing host (by new label or explicitly provided old label)
    found_idx = -1
    search_label = old_label if old_label else label
    
    for i, h in enumerate(hosts):
        if h['label'] == search_label:
            found_idx = i
            break
    
    if found_idx != -1:
        # Update in place to retain position
        hosts[found_idx] = {k: v for k, v in new_host.items() if k != 'old_label'}
    else:
        # Add to end
        hosts.append({k: v for k, v in new_host.items() if k != 'old_label'})
        
    curr_conf['HOSTS'] = hosts
    _, config_file, _ = get_config_paths()
    with open(config_file, 'w') as f: json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})

@app.route('/api/hosts/reorder', methods=['POST'])
@authenticated_only
def reorder_hosts():
    new_order = request.json # Expect list of labels
    curr_conf = get_config()
    hosts = curr_conf.get('HOSTS', [])
    
    reordered = []
    host_map = {h['label']: h for h in hosts}
    for label in new_order:
        if label in host_map:
            reordered.append(host_map[label])
            
    # Add any missing hosts at the end
    existing_labels = set(new_order)
    for h in hosts:
        if h['label'] not in existing_labels:
            reordered.append(h)
            
    curr_conf['HOSTS'] = reordered
    _, config_file, _ = get_config_paths()
    with open(config_file, 'w') as f: json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})

@app.route('/api/sessions/terminate', methods=['POST'])
@authenticated_only
def terminate_remote_session():
    data = request.json
    ssh_target = data.get('ssh_target')
    ssh_dir = data.get('ssh_dir')
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({"error": "Session ID required"}), 400
        
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return jsonify({"error": "Invalid SSH target"}), 400
        
        remote_prefix = get_remote_command_prefix(ssh_dir, GEMINI_BIN)
        remote_cmd = f"{remote_prefix} if command -v {GEMINI_BIN} >/dev/null 2>&1; then {GEMINI_BIN} --terminate {shlex.quote(str(session_id))}; fi"
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"
            
        cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no']
        _, _, ssh_dir_path = get_config_paths()
        known_hosts_path = os.path.join(ssh_dir_path, 'known_hosts')
        cmd.extend(['-o', f'UserKnownHostsFile={known_hosts_path}'])
        if os.path.exists(ssh_dir_path):
            for f in os.listdir(ssh_dir_path):
                if os.path.isfile(os.path.join(ssh_dir_path, f)) and f not in ['config', 'known_hosts'] and not f.endswith('.pub'):
                    cmd.extend(['-i', os.path.join(ssh_dir_path, f)])
        cmd.extend(['--', ssh_target, login_wrapped_cmd])
    else:
        cmd = [GEMINI_BIN, '--terminate', str(session_id)]
        
    try:
        subprocess.run(cmd)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/hosts/<label>', methods=['DELETE'])
@authenticated_only
def remove_host(label):
    if label == "local":
        return jsonify({"status": "error", "message": "Cannot delete local box"}), 403
    curr_conf = get_config()
    hosts = curr_conf.get('HOSTS', [])
    hosts = [h for h in hosts if h['label'] != label]
    curr_conf['HOSTS'] = hosts
    _, config_file, _ = get_config_paths()
    with open(config_file, 'w') as f: json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})

@app.route('/api/config', methods=['GET'])
@authenticated_only
def get_current_config():
    return jsonify(get_config())

@app.route('/api/config', methods=['POST'])
@authenticated_only
def update_config():
    new_conf = request.json
    curr_conf = get_config()
    curr_conf.update(new_conf)
    _, config_file, _ = get_config_paths()
    with open(config_file, 'w') as f: json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})

@app.route('/api/keys', methods=['GET'])
@authenticated_only
def list_ssh_keys():
    _, _, ssh_dir = get_config_paths()
    keys = []
    if os.path.exists(ssh_dir):
        for f in os.listdir(ssh_dir):
            if os.path.isfile(os.path.join(ssh_dir, f)) and f not in ['config', 'known_hosts']:
                keys.append(f)
    return jsonify(keys)

@app.route('/api/keys/public', methods=['GET'])
@authenticated_only
def get_public_key():
    _, _, ssh_dir = get_config_paths()
    pub_key_path = os.path.join(ssh_dir, "id_ed25519.pub")
    if os.path.exists(pub_key_path):
        with open(pub_key_path, 'r') as f:
            return jsonify({"key": f.read().strip()})
    return jsonify({"error": "Public key not found"}), 404

@app.route('/api/keys/rotate', methods=['POST'])
@authenticated_only
def rotate_instance_key():
    _, _, ssh_dir = get_config_paths()
    key_path = os.path.join(ssh_dir, 'id_ed25519')
    try:
        # Backup old key just in case
        if os.path.exists(key_path):
            timestamp = int(time.time())
            shutil.move(key_path, f"{key_path}.{timestamp}.bak")
            if os.path.exists(key_path + ".pub"):
                shutil.move(key_path + ".pub", f"{key_path}.{timestamp}.pub.bak")
        
        hostname = socket.gethostname()
        datestr = datetime.datetime.now().strftime('%Y%m%d')
        comment = f"gemini-webui-{hostname}-{datestr}"
        logger.info(f"Rotating instance SSH key with comment: {comment}...")
        subprocess.run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', key_path, '-C', comment], check=True)
        try:
            shutil.chown(key_path, user='node', group='node')
            shutil.chown(key_path + '.pub', user='node', group='node')
        except (LookupError, PermissionError):
            pass
        os.chmod(key_path, 0o600)
        
        with open(key_path + '.pub', 'r') as f:
            return jsonify({"status": "success", "key": f.read().strip()})
    except Exception as e:
        logger.error(f"Failed to rotate SSH key: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/keys/text', methods=['POST'])
@authenticated_only
def add_ssh_key_text():
    if request.content_length and request.content_length > 10 * 1024:
        return jsonify({"status": "error", "message": "Payload too large"}), 400

    data = request.json
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    raw_name = data.get('name')
    if not isinstance(raw_name, str):
        return jsonify({"status": "error", "message": "Invalid name format"}), 400

    name = secure_filename(raw_name)
    key_text = data.get('key')
    
    if not name or not key_text:
        return jsonify({"status": "error", "message": "Name and key are required"}), 400
        
    if not isinstance(key_text, str) or len(key_text) > 10 * 1024:
        return jsonify({"status": "error", "message": "Invalid key format or size"}), 400

    valid_prefixes = ('-----BEGIN ', 'ssh-', 'ecdsa-')
    if not any(key_text.lstrip().startswith(prefix) for prefix in valid_prefixes):
        return jsonify({"status": "error", "message": "Invalid SSH key format"}), 400

    if not key_text.endswith('\n'): key_text += '\n'
    _, _, ssh_dir = get_config_paths()
    save_path = os.path.join(ssh_dir, name)
    with open(save_path, 'w', encoding='utf-8') as f: f.write(key_text)
    os.chmod(save_path, 0o600)
    return jsonify({"status": "success", "filename": name})

@app.route('/api/keys/upload', methods=['POST'])
@authenticated_only
def upload_ssh_key():
    if request.content_length and request.content_length > 10 * 1024:
        return jsonify({"status": "error", "message": "Payload too large"}), 400

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"status": "error", "message": "Invalid filename"}), 400
        
    key_content = file.read(10 * 1024 + 1)
    if len(key_content) > 10 * 1024:
        return jsonify({"status": "error", "message": "File too large"}), 400

    try:
        key_text = key_content.decode('utf-8')
    except UnicodeDecodeError:
        return jsonify({"status": "error", "message": "Invalid file encoding"}), 400

    valid_prefixes = ('-----BEGIN ', 'ssh-', 'ecdsa-')
    if not any(key_text.lstrip().startswith(prefix) for prefix in valid_prefixes):
        return jsonify({"status": "error", "message": "Invalid SSH key format"}), 400

    _, _, ssh_dir = get_config_paths()
    save_path = os.path.join(ssh_dir, filename)
    with open(save_path, 'wb') as f:
        f.write(key_content)
    # Check if the file is a private key or a public key by looking at extension.
    # Public keys don't need strict permissions, but giving them 600 is fine.
    os.chmod(save_path, 0o600)
    return jsonify({"status": "success", "filename": filename})

@app.route('/api/keys/<filename>', methods=['DELETE'])
@authenticated_only
def remove_ssh_key(filename):
    filename = secure_filename(filename)
    _, _, ssh_dir = get_config_paths()
    path = os.path.join(ssh_dir, filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "File not found"}), 404

@app.route('/api/upload', methods=['POST'])
@authenticated_only
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    
    # preserve path structure if provided, otherwise fallback to standard secure_filename
    original_filename = file.filename
    if '/' in original_filename or '\\' in original_filename:
        # replace backslashes and normalize
        normalized_path = original_filename.replace('\\', '/')
        # extract directories and secure each part
        parts = [secure_filename(p) for p in normalized_path.split('/') if p]
        filename = '/'.join(parts)
    else:
        filename = secure_filename(file.filename)
        
    if not filename:
        return jsonify({"status": "error", "message": "Invalid filename"}), 400

    workspace_dir = os.environ.get("DATA_DIR", "/data")
    
    # Ensure save path is within workspace
    base_path = os.path.abspath(workspace_dir)
    save_path = os.path.abspath(os.path.join(base_path, filename))
    if not save_path.startswith(base_path):
        return jsonify({"status": "error", "message": "Access denied"}), 403
        
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)
    return jsonify({"status": "success", "filename": filename})

@app.route('/api/download/<path:filename>', methods=['GET'])
@authenticated_only
def download_file(filename):
    workspace_dir = os.environ.get("DATA_DIR", "/data")
    
    # Securely resolve the path and prevent directory traversal
    try:
        # We need to securely join the filename to the workspace_dir
        base_path = os.path.abspath(workspace_dir)
        target_path = os.path.abspath(os.path.join(base_path, filename))
        
        # Verify the target_path starts with the base_path
        if not target_path.startswith(base_path):
            return jsonify({"status": "error", "message": "Access denied"}), 403
            
        if not os.path.isfile(target_path):
            return jsonify({"status": "error", "message": f"File not found: {target_path}"}), 404
            
        # Get the directory and the actual filename to send
        dir_name = os.path.dirname(target_path)
        base_name = os.path.basename(target_path)
        
        print(f"DEBUG: sending {base_name} from {dir_name}")
        return send_from_directory(dir_name, base_name, as_attachment=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health')
def health_check_root():
    return jsonify({"status": "ok"})

@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    init_app()
    if not app.config.get('TESTING'):
        socketio.start_background_task(read_and_forward_pty_output)
        socketio.start_background_task(cleanup_orphaned_ptys)
        if os.environ.get('SKIP_PRELOADER') != 'true':
            socketio.start_background_task(background_session_preloader)
    
    debug_mode = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    use_reloader = os.environ.get('FLASK_USE_RELOADER', 'true').lower() == 'true'
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug_mode, use_reloader=use_reloader)
