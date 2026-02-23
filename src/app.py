import eventlet
eventlet.monkey_patch()

import os
import pty
import select
import signal
import struct
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
import ldap3

# Configuration Paths
DATA_DIR = os.environ.get('DATA_DIR', "/data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
SSH_DIR = os.path.join(DATA_DIR, ".ssh")

# Ensure directories exist
os.makedirs(SSH_DIR, mode=0o700, exist_ok=True)

def get_config():
    config = {
        "LDAP_SERVER": os.environ.get('LDAP_SERVER', 'ldaps://192.168.1.100'),
        "LDAP_BASE_DN": os.environ.get('LDAP_BASE_DN', 'CN=Users,DC=activedirectory,DC=adamoutler,DC=com'),
        "AD_BIND_USER_DN": os.environ.get('AD_BIND_USER_DN'),
        "AD_BIND_PASS": os.environ.get('AD_BIND_PASS'),
        "AUTHORIZED_GROUP": os.environ.get('AUTHORIZED_GROUP'),
        "FALLBACK_DOMAIN": os.environ.get('FALLBACK_DOMAIN', 'activedirectory.adamoutler.com'),
        "DEFAULT_SSH_TARGET": os.environ.get('DEFAULT_SSH_TARGET', 'adamoutler@192.168.1.101'),
        "DEFAULT_SSH_DIR": os.environ.get('DEFAULT_SSH_DIR', '~/oc'),
        "SECRET_KEY": os.environ.get('SECRET_KEY', 'stable-fallback-key-change-me'),
        "ALLOWED_ORIGINS": os.environ.get('ALLOWED_ORIGINS', '*')
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            logging.error(f"Error loading config file: {e}")
            
    return config

config = get_config()

# SECURITY PARADIGM: Fail-Closed Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Handle proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# SECURITY PARADIGM: Defense in Depth (Secure Cookies)
app.config.update(
    SECRET_KEY=config.get('SECRET_KEY'),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# SECURITY PARADIGM: Secure Headers (CSP, HSTS, etc.)
csp = {
    'default-src': "'self'",
    'script-src': [
        "'self'",
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com',
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
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com'
    ]
}
# force_https and strict_transport_security are disabled because the reverse proxy handles SSL.
# session_cookie_secure is disabled to prevent issues if the proxy-app link is HTTP.
Talisman(app, 
         content_security_policy=csp, 
         force_https=False, 
         strict_transport_security=False,
         session_cookie_secure=False)

# VULNERABILITY FIX: Restrict CORS
allowed_origins = config.get('ALLOWED_ORIGINS', '*')
if allowed_origins != '*':
    allowed_origins = allowed_origins.split(',')
socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='eventlet')

LDAP_SERVER = config.get('LDAP_SERVER')
LDAP_BASE_DN = config.get('LDAP_BASE_DN')
AD_BIND_USER_DN = config.get('AD_BIND_USER_DN')
AD_BIND_PASS = config.get('AD_BIND_PASS')
AUTHORIZED_GROUP = config.get('AUTHORIZED_GROUP')
FALLBACK_DOMAIN = config.get('FALLBACK_DOMAIN')

# SSH Defaults
DEFAULT_SSH_TARGET = config.get('DEFAULT_SSH_TARGET')
DEFAULT_SSH_DIR = config.get('DEFAULT_SSH_DIR')

@app.before_request
def log_request_info():
    logger.debug('Request: %s %s [Scheme: %s]', request.method, request.url, request.scheme)

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.svg')

def sanitize_ldap_input(input_str):
    return re.sub(r'[()\*\\\0]', '', input_str) if input_str else ""

def check_auth(username, password):
    try:
        username = sanitize_ldap_input(username)
        server = ldap3.Server(LDAP_SERVER, get_info=ldap3.ALL, connect_timeout=2)
        
        if AD_BIND_USER_DN and AD_BIND_PASS:
            conn = ldap3.Connection(server, user=AD_BIND_USER_DN, password=AD_BIND_PASS, auto_bind=True)
            search_filter = f"(&(objectClass=*)(sAMAccountName={username}))"
            conn.search(LDAP_BASE_DN, search_filter, attributes=['memberOf'])
            
            if not conn.entries:
                logger.warning(f"Auth failure: User {username} not found.")
                return False
                
            user_entry = conn.entries[0]
            user_dn = user_entry.entry_dn
            
            if AUTHORIZED_GROUP:
                member_of = user_entry.memberOf.values if 'memberOf' in user_entry else []
                group_match = any(AUTHORIZED_GROUP.lower() in group.lower() for group in member_of)
                if not group_match:
                    logger.warning(f"Auth failure: User {username} not in group {AUTHORIZED_GROUP}")
                    return False
                    
            ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
            return True
        else:
            user_dn = f"{username}@{FALLBACK_DOMAIN}"
            ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
            return True
            
    except Exception:
        logger.error("LDAP authentication process failed.")
        return False

def authenticate():
    return Response(
    'Login Required', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

@app.before_request
def require_auth():
    if os.environ.get('BYPASS_AUTH_FOR_TESTING') == 'true':
        session['authenticated'] = True
        return
        
    if not LDAP_SERVER:
        logger.critical("LDAP_SERVER not configured. Denying access.")
        return authenticate()
        
    auth = request.authorization
    if auth and check_auth(auth.username, auth.password):
        session['authenticated'] = True
    else:
        return authenticate()

def authenticated_only(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get('authenticated'):
            disconnect()
        else:
            return f(*args, **kwargs)
    return wrapped

fd = None
child_pid = None
# Store current session config for automatic restarts
current_config = {"resume": True, "rows": 24, "cols": 80, "ssh_target": DEFAULT_SSH_TARGET, "ssh_dir": DEFAULT_SSH_DIR}

def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

def read_and_forward_pty_output():
    global fd
    max_read_bytes = 1024 * 20
    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
    while True:
        if fd:
            try:
                timeout_sec = 0.1
                (data_ready, _, _) = select.select([fd], [], [], timeout_sec)
                if data_ready:
                    raw_data = os.read(fd, max_read_bytes)
                    if raw_data:
                        output = decoder.decode(raw_data)
                        if output:
                            socketio.emit("pty-output", {"output": output})
            except Exception:
                pass
        socketio.sleep(0.01)

def start_gemini(resume=False, rows=24, cols=80, ssh_target=None, ssh_dir=None):
    global fd, child_pid, current_config
    current_config = {"resume": resume, "rows": rows, "cols": cols, "ssh_target": ssh_target, "ssh_dir": ssh_dir}
    
    if child_pid:
        try:
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
        except Exception:
            pass
    
    child_pid, fd = pty.fork()
    if child_pid == 0:
        os.environ['TERM'] = 'xterm-256color'
        os.environ['COLORTERM'] = 'truecolor'
        
        if ssh_target:
            # Start via SSH. -t forces pty allocation for the remote process.
            # Explicitly export TERM and COLORTERM to ensure the remote session supports colors.
            remote_env = "export TERM=xterm-256color; export COLORTERM=truecolor;"
            remote_cmd = f"{remote_env} cd {ssh_dir} && gemini" if ssh_dir else f"{remote_env} gemini"
            if resume:
                remote_cmd += " -r"
            
            cmd = ['ssh', '-X', '-t']
            
            # Add identity files from /data/.ssh
            if os.path.exists(SSH_DIR):
                for f in os.listdir(SSH_DIR):
                    if not f.endswith('.pub') and not f.startswith('config'):
                        key_path = os.path.join(SSH_DIR, f)
                        # Basic check if it's a file and not a directory
                        if os.path.isfile(key_path):
                            cmd.extend(['-i', key_path])
            
            # Disable strict host key checking to avoid interactive prompts
            cmd.extend(['-o', 'StrictHostKeyChecking=no'])
            
            cmd.extend([ssh_target, remote_cmd])
        else:
            # Start local
            cmd = ['gemini']
            if resume:
                cmd.append('-r')
                
        os.execvp(cmd[0], cmd)
        os._exit(0)
    else:
        try:
            set_winsize(fd, rows, cols)
        except Exception:
            pass

@app.route('/')
def index():
    return render_template('index.html', 
                          default_target=DEFAULT_SSH_TARGET, 
                          default_dir=DEFAULT_SSH_DIR)

@app.route('/api/config', methods=['GET'])
@authenticated_only
def get_current_config():
    return jsonify(get_config())

@app.route('/api/config', methods=['POST'])
@authenticated_only
def update_config():
    new_config = request.json
    current_config = get_config()
    current_config.update(new_config)
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(current_config, f, indent=4)
    
    return jsonify({"status": "success"})

@app.route('/api/keys', methods=['POST'])
@authenticated_only
def add_ssh_key():
    if 'key' not in request.files:
        return jsonify({"status": "error", "message": "No key file provided"}), 400
    
    file = request.files['key']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    
    filename = secure_filename(file.filename)
    save_path = os.path.join(SSH_DIR, filename)
    file.save(save_path)
    os.chmod(save_path, 0o600)
    
    return jsonify({"status": "success", "filename": filename})

@socketio.on('pty-input')
@authenticated_only
def pty_input(data):
    global fd
    if fd:
        try:
            os.write(fd, data['input'].encode('utf-8'))
        except Exception:
            pass

@socketio.on('resize')
@authenticated_only
def resize(data):
    global fd
    if fd:
        try:
            set_winsize(fd, data['rows'], data['cols'])
        except Exception:
            pass

@socketio.on('restart')
@authenticated_only
def handle_restart(data):
    resume = data.get('resume', False)
    rows = data.get('rows', 24)
    cols = data.get('cols', 80)
    ssh_target = data.get('ssh_target')
    ssh_dir = data.get('ssh_dir')
    start_gemini(resume, rows=rows, cols=cols, ssh_target=ssh_target, ssh_dir=ssh_dir)

def monitor_gemini():
    global child_pid, fd, current_config
    while True:
        if child_pid:
            try:
                pid, status = os.waitpid(child_pid, os.WNOHANG)
                if pid == child_pid:
                    logger.info("Gemini process exited, restarting with current config...")
                    start_gemini(**current_config)
            except ChildProcessError:
                start_gemini(**current_config)
        socketio.sleep(1)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    start_gemini(resume=True, ssh_target=DEFAULT_SSH_TARGET, ssh_dir=DEFAULT_SSH_DIR)
    socketio.start_background_task(read_and_forward_pty_output)
    socketio.start_background_task(monitor_gemini)
    socketio.run(app, host='0.0.0.0', port=port)
