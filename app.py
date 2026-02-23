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
from functools import wraps
from flask import Flask, render_template, request, Response, session
from flask_socketio import SocketIO, disconnect
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix
import ldap3
import eventlet

eventlet.monkey_patch()

# SECURITY PARADIGM: Fail-Closed Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Handle proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# SECURITY PARADIGM: Defense in Depth (Secure Cookies)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'stable-fallback-key-change-me'),
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
Talisman(app, content_security_policy=csp, force_https=False)

# VULNERABILITY FIX: Restrict CORS
allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*')
if allowed_origins != '*':
    allowed_origins = allowed_origins.split(',')
socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='eventlet')

LDAP_SERVER = os.environ.get('LDAP_SERVER', 'ldaps://192.168.1.100')
LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN', 'CN=Users,DC=activedirectory,DC=adamoutler,DC=com')
AD_BIND_USER_DN = os.environ.get('AD_BIND_USER_DN')
AD_BIND_PASS = os.environ.get('AD_BIND_PASS')
AUTHORIZED_GROUP = os.environ.get('AUTHORIZED_GROUP')
FALLBACK_DOMAIN = os.environ.get('FALLBACK_DOMAIN', 'activedirectory.adamoutler.com')

# SSH Defaults
DEFAULT_SSH_TARGET = os.environ.get('DEFAULT_SSH_TARGET', 'adamoutler@192.168.1.101')
DEFAULT_SSH_DIR = os.environ.get('DEFAULT_SSH_DIR', '~/oc')

@app.route('/favicon.ico')
def favicon():
    return Response(status=404)

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
            remote_cmd = f"cd {ssh_dir} && gemini" if ssh_dir else "gemini"
            if resume:
                remote_cmd += " -r"
            cmd = ['ssh', '-t', ssh_target, remote_cmd]
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
    start_gemini(resume=True, ssh_target=DEFAULT_SSH_TARGET, ssh_dir=DEFAULT_SSH_DIR)
    socketio.start_background_task(read_and_forward_pty_output)
    socketio.start_background_task(monitor_gemini)
    socketio.run(app, host='0.0.0.0', port=5000)
