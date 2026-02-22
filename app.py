import os
import pty
import select
import signal
import struct
import fcntl
import termios
import re
import logging # Added for secure logging
from functools import wraps
from flask import Flask, render_template, request, Response, session
from flask_socketio import SocketIO, disconnect
from flask_talisman import Talisman # Added for security headers
import ldap3
import eventlet

eventlet.monkey_patch()

# SECURITY PARADIGM: Fail-Closed Logging
# We use a proper logger and avoid printing raw exceptions to prevent data leaks.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# SECURITY PARADIGM: Defense in Depth (Secure Cookies)
# Session cookies are locked down to prevent theft via XSS (HttpOnly) 
# and ensure they are only sent over HTTPS (Secure).
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', os.urandom(24).hex()),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# SECURITY PARADIGM: Secure Headers (CSP, HSTS, etc.)
# Talisman automatically adds essential security headers.
# We allow inline scripts for xterm.js but restrict origins.
csp = {
    'default-src': '\'self\'',
    'script-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com',
        '\'unsafe-inline\'' # Required for xterm initialization in templates
    ],
    'style-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net',
        '\'unsafe-inline\''
    ],
    'connect-src': ['\'self\'', 'ws:', 'wss:'] # Allow WebSockets
}
Talisman(app, content_security_policy=csp)

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

def sanitize_ldap_input(input_str):
    # SECURITY PARADIGM: Input Sanitization
    # Prevents LDAP Injection by stripping special characters used in filters.
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
                    
            user_conn = ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
            return True
        else:
            user_dn = f"{username}@{FALLBACK_DOMAIN}"
            conn = ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
            return True
            
    except Exception:
        # SECURITY PARADIGM: No Sensitive Data Leakage
        # We log a generic message and avoid exposing LDAP server details.
        logger.error("LDAP authentication process failed.")
        return False

def authenticate():
    return Response(
    'Login Required', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

@app.before_request
def require_auth():
    # SECURITY PARADIGM: Fail-Closed
    # If the environment is not properly configured, we deny all access.
    if not LDAP_SERVER:
        logger.critical("LDAP_SERVER not configured. Denying access.")
        return authenticate()
        
    auth = request.authorization
    if auth and check_auth(auth.username, auth.password):
        session['authenticated'] = True
    else:
        return authenticate()

# VULNERABILITY FIX: Socket.IO Authentication Decorator
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

def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

def read_and_forward_pty_output():
    global fd
    max_read_bytes = 1024 * 20
    while True:
        if fd:
            try:
                timeout_sec = 0.1
                (data_ready, _, _) = select.select([fd], [], [], timeout_sec)
                if data_ready:
                    output = os.read(fd, max_read_bytes).decode('utf-8', 'replace')
                    if output:
                        socketio.emit("pty-output", {"output": output})
            except Exception as e:
                pass
        socketio.sleep(0.01)

def start_gemini(resume=False):
    global fd, child_pid
    if child_pid:
        try:
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
        except:
            pass
    
    child_pid, fd = pty.fork()
    if child_pid == 0:
        os.environ['TERM'] = 'xterm-256color'
        cmd = ['gemini']
        if resume:
            cmd.append('-r')
        os.execvp('gemini', cmd)
        os._exit(0)
    else:
        pass

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('pty-input')
@authenticated_only
def pty_input(data):
    global fd
    if fd:
        try:
            os.write(fd, data['input'].encode('utf-8'))
        except:
            pass

@socketio.on('resize')
@authenticated_only
def resize(data):
    global fd
    if fd:
        try:
            set_winsize(fd, data['rows'], data['cols'])
        except:
            pass

@socketio.on('restart')
@authenticated_only
def handle_restart(data):
    resume = data.get('resume', False)
    start_gemini(resume)

def monitor_gemini():
    global child_pid, fd
    while True:
        if child_pid:
            try:
                pid, status = os.waitpid(child_pid, os.WNOHANG)
                if pid == child_pid:
                    logger.info("Gemini exited, restarting...")
                    start_gemini(resume=True)
            except ChildProcessError:
                start_gemini(resume=True)
        socketio.sleep(1)

if __name__ == '__main__':
    start_gemini(resume=True)
    socketio.start_background_task(read_and_forward_pty_output)
    socketio.start_background_task(monitor_gemini)
    socketio.run(app, host='0.0.0.0', port=5000)