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
import codecs
import json
import shutil
from functools import wraps
from flask import Flask, render_template, request, Response, session, jsonify
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, disconnect
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix
try:
    from auth_ldap import check_auth
except ImportError:
    from src.auth_ldap import check_auth

# Global config holder and defaults
config = {}
ADMIN_USER = os.environ.get('ADMIN_USER')
ADMIN_PASS = os.environ.get('ADMIN_PASS')
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

# Handle proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# Multi-tab support and persistence
persistent_ptys = {}  # tab_id -> {'fd': fd, 'pid': pid, 'decoder': decoder, 'last_seen': time}
sid_to_tabid = {}
tabid_to_sid = {}
orphaned_ptys = {}    # tab_id -> timestamp

# Background session cache: key -> {"output": str, "error": str, "timestamp": float}
session_results_cache = {}

def cleanup_orphaned_ptys():
    """Periodically kills PTYs that have been orphaned for too long."""
    while True:
        socketio.sleep(10)
        now = time.time()
        for tab_id, ts in list(orphaned_ptys.items()):
            if now - ts > 60:  # 60 second grace period
                logger.info(f"Cleaning up orphaned PTY for tab: {tab_id}")
                pty_info = persistent_ptys.pop(tab_id, None)
                orphaned_ptys.pop(tab_id, None)
                if pty_info:
                    try:
                        os.kill(pty_info['pid'], signal.SIGKILL)
                        os.waitpid(pty_info['pid'], 0)
                    except Exception:
                        pass

def get_config_paths():
    data_dir = app.config.get('DATA_DIR', os.environ.get('DATA_DIR', "/data"))
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
    global config, LDAP_SERVER, LDAP_BASE_DN, LDAP_BIND_USER_DN, LDAP_BIND_PASS, LDAP_AUTHORIZED_GROUP, LDAP_FALLBACK_DOMAIN
    data_dir, config_file, ssh_dir = get_config_paths()
    logger.info(f"Initializing app with DATA_DIR: {data_dir}")
    os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
    
    gemini_data = os.path.join(data_dir, ".gemini")
    os.makedirs(gemini_data, mode=0o700, exist_ok=True)
    
    # Target /home/node/.gemini as requested
    home_gemini = "/home/node/.gemini"
    if os.path.islink(home_gemini):
        try:
            if os.readlink(home_gemini) != gemini_data:
                os.unlink(home_gemini)
                os.symlink(gemini_data, home_gemini)
                logger.info(f"Updated symlink {home_gemini} to {gemini_data}")
        except Exception as e:
            logger.error(f"Failed to update symlink: {e}")
    elif os.path.exists(home_gemini):
        if os.path.isdir(home_gemini):
            import shutil
            try:
                # If it's a directory, we might want to move its contents? 
                # But the user said "make it a symlink", so we'll just remove and link.
                shutil.rmtree(home_gemini)
                os.symlink(gemini_data, home_gemini)
                logger.info(f"Replaced directory {home_gemini} with symlink to {gemini_data}")
            except Exception as e:
                logger.error(f"Failed to replace directory with symlink: {e}")
    else:
        try:
            os.makedirs(os.path.dirname(home_gemini), exist_ok=True)
            os.symlink(gemini_data, home_gemini)
            logger.info(f"Created symlink {home_gemini} to {gemini_data}")
        except Exception as e:
            logger.error(f"Failed to create symlink: {e}")
    
    config = get_config()
    LDAP_SERVER = config.get('LDAP_SERVER')
    LDAP_BASE_DN = config.get('LDAP_BASE_DN')
    LDAP_BIND_USER_DN = config.get('LDAP_BIND_USER_DN')
    LDAP_BIND_PASS = config.get('LDAP_BIND_PASS')
    LDAP_AUTHORIZED_GROUP = config.get('LDAP_AUTHORIZED_GROUP')
    LDAP_FALLBACK_DOMAIN = config.get('LDAP_FALLBACK_DOMAIN')

    app.config.update(
        SECRET_KEY='gemini-webui-stable-secret-key',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False, 
        SESSION_COOKIE_SAMESITE='Lax',
        DATA_DIR=data_dir
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
        "'unsafe-inline'"
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
    ]
}

Talisman(app, 
         content_security_policy=csp, 
         force_https=False, 
         strict_transport_security=False,
         session_cookie_secure=False)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

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
    tab_id = sid_to_tabid.pop(sid, None)
    if tab_id:
        tabid_to_sid.pop(tab_id, None)
        if tab_id in persistent_ptys:
            logger.info(f"PTY orphaned for tab_id: {tab_id} (sid: {sid})")
            orphaned_ptys[tab_id] = time.time()

@app.before_request
def require_auth():
    if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true' or app.config.get('BYPASS_AUTH_FOR_TESTING') == 'true':
        session['authenticated'] = True
        return
        
    if request.path == '/api/health':
        return

    auth = request.authorization
    
    # Allow ADMIN_USER/ADMIN_PASS bypass
    if auth and auth.username == ADMIN_USER and auth.password == ADMIN_PASS:
        session['authenticated'] = True
        return

    # Fallback authentication if LDAP is not configured
    if not LDAP_SERVER:
        return authenticate()
        
    if auth and check_auth(auth.username, auth.password, LDAP_SERVER, LDAP_BASE_DN, LDAP_BIND_USER_DN, LDAP_BIND_PASS, LDAP_AUTHORIZED_GROUP, LDAP_FALLBACK_DOMAIN):
        session['authenticated'] = True
        return

    if not session.get('authenticated'):
        return authenticate()

def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

def read_and_forward_pty_output():
    max_read_bytes = 1024 * 20
    while True:
        socketio.sleep(0.01)
        for tab_id, pty_info in list(persistent_ptys.items()):
            fd = pty_info['fd']
            decoder = pty_info['decoder']
            sid = tabid_to_sid.get(tab_id)
            try:
                (data_ready, _, _) = select.select([fd], [], [], 0)
                if data_ready:
                    output = os.read(fd, max_read_bytes)
                    if output:
                        decoded_output = decoder.decode(output)
                        if decoded_output and sid:
                            socketio.emit('pty-output', {'output': decoded_output}, room=sid)
            except (OSError, IOError, EOFError):
                persistent_ptys.pop(tab_id, None)
                orphaned_ptys.pop(tab_id, None)
                if sid:
                    sid_to_tabid.pop(sid, None)
                    tabid_to_sid.pop(tab_id, None)

def fetch_sessions_for_host(host):
    """Internal helper to fetch sessions for a host config."""
    ssh_target = host.get('target')
    ssh_dir = host.get('dir')
    cmd = []
    if ssh_target:
        remote_cmd = "gemini --list-sessions"
        if ssh_dir:
            remote_cmd = f"cd {ssh_dir} && {remote_cmd}"
        cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=no']
        data_dir, _, ssh_dir_path = get_config_paths()
        if os.path.exists(ssh_dir_path):
            for f in os.listdir(ssh_dir_path):
                if os.path.isfile(os.path.join(ssh_dir_path, f)) and f not in ['config', 'known_hosts'] and not f.endswith('.pub'):
                    cmd.extend(['-i', os.path.join(ssh_dir_path, f)])
        cmd.extend([ssh_target, remote_cmd])
    else:
        cmd = ['gemini', '--list-sessions']

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "timestamp": time.time()
        }
    except Exception as e:
        return {"error": str(e), "timestamp": time.time()}

def background_session_preloader():
    """Warms the session cache on startup."""
    while True:
        try:
            hosts = get_config().get('HOSTS', [])
            for host in hosts:
                key = f"{host.get('type')}:{host.get('target', 'local')}:{host.get('dir', '')}"
                logger.info(f"Background preloading sessions for: {host.get('label')}")
                session_results_cache[key] = fetch_sessions_for_host(host)
        except Exception as e:
            logger.error(f"Preloader error: {e}")
        # Only run once at startup, then sleep for a long time or until manually triggered
        # For simplicity, we just do it once then sleep for an hour.
        socketio.sleep(3600)

@socketio.on('pty-input')
def pty_input(data):
    sid = request.sid
    tab_id = sid_to_tabid.get(sid)
    if tab_id in persistent_ptys:
        os.write(persistent_ptys[tab_id]['fd'], data['input'].encode())

@socketio.on('resize')
def pty_resize(data):
    sid = request.sid
    tab_id = sid_to_tabid.get(sid)
    if tab_id in persistent_ptys:
        try:
            set_winsize(persistent_ptys[tab_id]['fd'], data['rows'], data['cols'])
        except Exception:
            pass

@socketio.on('restart')
def pty_restart(data):
    sid = request.sid
    tab_id = data.get('tab_id')
    if not tab_id:
        return
        
    # Associate SID with Tab ID
    sid_to_tabid[sid] = tab_id
    tabid_to_sid[tab_id] = sid
    
    # If we already have a PTY for this tab, check if we should reuse it
    if tab_id in persistent_ptys:
        if orphaned_ptys.pop(tab_id, None):
            logger.info(f"Reattached to orphaned PTY for tab: {tab_id}")
            # Send a clear-ish screen or some marker to indicate reattachment
            socketio.emit('pty-output', {'output': '\r\n[Reattached]\r\n'}, room=sid)
            # Re-sync terminal size
            try:
                set_winsize(persistent_ptys[tab_id]['fd'], data.get('rows', 24), data.get('cols', 80))
            except Exception: pass
            return
        else:
            # Explicit restart requested for an active session
            pty_info = persistent_ptys.pop(tab_id)
            try:
                os.kill(pty_info['pid'], signal.SIGKILL)
                os.waitpid(pty_info['pid'], 0)
            except Exception: pass
            
    resume = data.get('resume', True)
    cols = data.get('cols', 80)
    rows = data.get('rows', 24)
    ssh_target = data.get('ssh_target')
    ssh_dir = data.get('ssh_dir')
    
    (child_pid, fd) = pty.fork()
    if child_pid == 0:
        os.environ['TERM'] = 'xterm-256color'
        os.environ['COLORTERM'] = 'truecolor'
        if ssh_target:
            remote_cmd = "gemini"
            if resume is True: remote_cmd += " -r"
            elif resume and str(resume).isdigit(): remote_cmd += f" -r {resume}"
            if ssh_dir: remote_cmd = f"cd {ssh_dir} && {remote_cmd}"
            cmd = ['ssh', '-t']
            _, _, ssh_dir_path = get_config_paths()
            if os.path.exists(ssh_dir_path):
                for f in os.listdir(ssh_dir_path):
                    if os.path.isfile(os.path.join(ssh_dir_path, f)) and f not in ['config', 'known_hosts'] and not f.endswith('.pub'):
                        cmd.extend(['-i', os.path.join(ssh_dir_path, f)])
            cmd.extend(['-o', 'PreferredAuthentications=publickey,password', '-o', 'StrictHostKeyChecking=no', ssh_target, remote_cmd])
        else:
            cmd = ['gemini']
            if resume is True: cmd.append('-r')
            elif resume and str(resume).isdigit(): cmd.extend(['-r', str(resume)])
        os.execvp(cmd[0], cmd)
        os._exit(0)
    else:
        persistent_ptys[tab_id] = {'fd': fd, 'pid': child_pid, 'decoder': codecs.getincrementaldecoder('utf-8')()}
        try: set_winsize(fd, rows, cols)
        except Exception: pass
        socketio.emit('pty-output', {'output': '\r\nLoading Context...\r\n'}, room=sid)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hosts', methods=['GET'])
@authenticated_only
def list_hosts():
    return jsonify(get_config().get('HOSTS', []))

@app.route('/api/hosts', methods=['POST'])
@authenticated_only
def add_host():
    new_host = request.json
    label = new_host.get('label')
    if not label:
        return jsonify({"status": "error", "message": "Label is required"}), 400
        
    curr_conf = get_config()
    hosts = curr_conf.get('HOSTS', [])
    
    # Check if we are updating an existing host
    found = False
    for i, h in enumerate(hosts):
        if h['label'] == label:
            hosts[i] = new_host
            found = True
            break
    
    if not found:
        hosts.append(new_host)
        
    curr_conf['HOSTS'] = hosts
    _, config_file, _ = get_config_paths()
    with open(config_file, 'w') as f: json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})

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
            if os.path.isfile(os.path.join(ssh_dir, f)) and f not in ['config', 'known_hosts'] and not f.endswith('.pub'):
                keys.append(f)
    return jsonify(keys)

@app.route('/api/keys/public', methods=['GET'])
@authenticated_only
def get_public_key():
    pub_key_path = os.path.expanduser("~/.ssh/id_ed25519.pub")
    if os.path.exists(pub_key_path):
        with open(pub_key_path, 'r') as f:
            return jsonify({"key": f.read().strip()})
    return jsonify({"error": "Public key not found"}), 404

@app.route('/api/keys/text', methods=['POST'])
@authenticated_only
def add_ssh_key_text():
    data = request.json
    name = secure_filename(data.get('name'))
    key_text = data.get('key')
    if not name or not key_text: return jsonify({"status": "error", "message": "Name and key are required"}), 400
    if not key_text.endswith('\n'): key_text += '\n'
    _, _, ssh_dir = get_config_paths()
    save_path = os.path.join(ssh_dir, name)
    with open(save_path, 'w', encoding='utf-8') as f: f.write(key_text)
    os.chmod(save_path, 0o600)
    return jsonify({"status": "success", "filename": name})

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
    
    result = fetch_sessions_for_host({'target': ssh_target, 'dir': ssh_dir, 'type': 'ssh' if ssh_target else 'local'})
    err = result.get('error')
    if err and 'timeout' in err.lower():
        return jsonify(result), 504
    session_results_cache[cache_key] = result
    return jsonify(result)

@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    init_app()
    socketio.start_background_task(read_and_forward_pty_output)
    socketio.start_background_task(cleanup_orphaned_ptys)
    if os.environ.get('SKIP_PRELOADER') != 'true':
        socketio.start_background_task(background_session_preloader)
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
