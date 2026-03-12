import os
try:
    from config import env_config
except ImportError:
    from src.config import env_config
import re
import shlex
import subprocess
import time

def validate_ssh_target(target):
    """Ensure SSH target is in a safe format (user@host, host, or host:port)."""
    if not target:
        return False
    # Allow alphanumeric, dots, hyphens, optional user@, and optional :port
    return bool(re.match(r'^([a-zA-Z0-9.-]+@)?[a-zA-Z0-9.-]+(:[0-9]+)?$', target))

def build_ssh_args(ssh_target, ssh_dir_path):
    """Builds common SSH connection arguments."""
    cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no']
    known_hosts_path = os.path.join(ssh_dir_path, 'known_hosts')
    if not os.access(ssh_dir_path, os.W_OK) and not os.access(known_hosts_path, os.W_OK):
        known_hosts_path = "/dev/null"
    cmd.extend(['-o', f'UserKnownHostsFile={known_hosts_path}'])
    
    if os.path.exists(ssh_dir_path):
        for f in os.listdir(ssh_dir_path):
            if os.path.isfile(os.path.join(ssh_dir_path, f)) and f not in ['config', 'known_hosts'] and not f.endswith('.pub'):
                cmd.extend(['-i', os.path.join(ssh_dir_path, f)])
    return cmd

import shlex

def get_remote_command_prefix(ssh_dir, gemini_bin='gemini', env_vars=None):
    """Builds a robust prefix for remote commands to ensure PATH and environment are loaded."""
    # Common color and path exports
    prefix = "export PATH=\"$PATH:$HOME/.local/bin:$HOME/bin\"; "
    prefix += "export TERM=xterm-256color; export COLORTERM=truecolor; export FORCE_COLOR=3; "

    if env_vars and isinstance(env_vars, dict):
        for k, v in env_vars.items():
            if isinstance(k, str) and isinstance(v, str):
                prefix += f"export {k}={shlex.quote(v)}; "

    # Source profiles quietly to populate PATH (e.g. npm globals, nvm, etc.)
    prefix += "source ~/.profile 2>/dev/null; source ~/.bash_profile 2>/dev/null; source ~/.bashrc 2>/dev/null; "    
    if ssh_dir and ssh_dir != "~":
        if ssh_dir.startswith('~'):
            suffix = ssh_dir[1:]
            prefix += f"cd ~{shlex.quote(suffix)} 2>/dev/null || cd ~; "
        else:
            prefix += f"cd {shlex.quote(ssh_dir)} 2>/dev/null || cd ~; "
            
    return prefix

def fetch_sessions_for_host(host, ssh_dir_path, gemini_bin='gemini'):
    """Internal helper to fetch sessions for a host config."""
    ssh_target = host.get('target')
    ssh_dir = host.get('dir')
    env_vars = host.get('env_vars')
    cmd = []
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return {"error": "Invalid SSH target format", "timestamp": time.time()}
            
        quoted_gemini = shlex.quote(gemini_bin)
        gemini_list_cmd = f"{quoted_gemini} --list-sessions"
        remote_prefix = get_remote_command_prefix(ssh_dir, gemini_bin, env_vars=env_vars)
        
        # Check for gemini before running list-sessions to avoid ugly bash errors
        remote_cmd = f"{remote_prefix} if command -v {quoted_gemini} >/dev/null 2>&1; then {gemini_list_cmd}; else exit 0; fi"
            
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"

        cmd = build_ssh_args(ssh_target, ssh_dir_path)

        clean_target = ssh_target
        if ':' in ssh_target:
            parts = ssh_target.rsplit(':', 1)
            if parts[1].isdigit():
                clean_target = parts[0]
                cmd.extend(['-p', parts[1]])

        cmd.extend(['--', clean_target, login_wrapped_cmd])
    else:
        # Use workspace for local session listing to match startSession
        data_dir = env_config.DATA_DIR
        work_dir = os.path.join(data_dir, "workspace")
        if os.path.exists(work_dir):
            cmd = ['/bin/sh', '-c', f"cd {shlex.quote(work_dir)} && {shlex.quote(gemini_bin)} --list-sessions"]
        else:
            cmd = [gemini_bin, '--list-sessions']

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Suppress auth errors from the CLI - just show as "no sessions"
        if result.returncode != 0 and ("Please set an Auth method" in result.stderr or "GEMINI_API_KEY" in result.stderr):
            return {
                "output": "",
                "error": None,
                "timestamp": time.time()
            }
        return {
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "timestamp": time.time()
        }
    except subprocess.TimeoutExpired:
        return {"error": "Could not establish connection (timed out)", "timestamp": time.time()}
    except Exception:
        return {"error": "Connection failed", "timestamp": time.time()}

def _wrap_with_multiplexer(cmd):
    """Wraps the terminal command in a multiplexer (tmux or dtach) to prevent visual corruption on detach/re-attach."""
    if env_config.SKIP_MULTIPLEXER:
        return cmd
        
    import shutil
    import uuid
    session_id = f"gemini_{uuid.uuid4().hex[:8]}"
    
    if shutil.which('tmux'):
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        return ['tmux', 'new-session', '-A', '-s', session_id, cmd_str]
    elif shutil.which('dtach'):
        return ['dtach', '-A', f"/tmp/{session_id}", '-r', 'winch'] + cmd
    
    return cmd

def build_terminal_command(ssh_target, ssh_dir, resume, ssh_dir_path, gemini_bin='gemini', env_vars=None, is_fake=False, executable_override=None):
    """Builds the shell/ssh command array for os.execvp when starting a PTY."""
    if executable_override:
        return shlex.split(executable_override)
    if is_fake:
        cmd = shlex.split(gemini_bin)
        return cmd
        
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return None # Invalid target
            
        quoted_gemini = shlex.quote(gemini_bin)
        gemini_base_cmd = quoted_gemini
        if resume is True or str(resume).lower() == 'true':
            gemini_base_cmd += " -r"
        elif str(resume).lower() == 'new':
            pass # Just run gemini without -r to start a fresh session
        elif resume and str(resume).lower() != 'false':
            gemini_base_cmd += f" -r {shlex.quote(str(resume))}"
        
        remote_prefix = get_remote_command_prefix(ssh_dir, gemini_bin, env_vars=env_vars)
        
        # Smart command construction: check for gemini, drop to shell if missing
        remote_cmd = f"{remote_prefix} if command -v {quoted_gemini} >/dev/null 2>&1; then "
        remote_cmd += f"{gemini_base_cmd}; "
        remote_cmd += "else "
        remote_cmd += "printf '\\r\\n\\033[1;31mError: gemini CLI not found on remote host.\\033[0m\\r\\n'; "
        remote_cmd += "printf 'Please install it from: \\033[1;34mhttps://geminicli.com/\\033[0m\\r\\n\\r\\n'; "
        remote_cmd += "exec $SHELL; "
        remote_cmd += "fi"
        
        # Wrap in login shell to ensure .profile/.bash_profile PATH is loaded
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"
            
        cmd = ['ssh', '-t']
        
        known_hosts_path = os.path.join(ssh_dir_path, 'known_hosts')
        if not os.access(ssh_dir_path, os.W_OK) and not os.access(known_hosts_path, os.W_OK):
            known_hosts_path = "/dev/null"
        cmd.extend(['-o', f'UserKnownHostsFile={known_hosts_path}'])
        
        if os.path.exists(ssh_dir_path):
            for f in os.listdir(ssh_dir_path):
                if os.path.isfile(os.path.join(ssh_dir_path, f)) and f not in ['config', 'known_hosts'] and not f.endswith('.pub'):
                    cmd.extend(['-i', os.path.join(ssh_dir_path, f)])
        cmd.extend([
            '-o', 'PreferredAuthentications=publickey,password', 
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ServerAliveInterval=60',
            '-o', 'ServerAliveCountMax=120', # Allow up to 2 hours of silence
        ])
        
        clean_target = ssh_target
        if ':' in ssh_target:
            parts = ssh_target.rsplit(':', 1)
            if parts[1].isdigit():
                clean_target = parts[0]
                cmd.extend(['-p', parts[1]])
                
        cmd.extend(['--', clean_target, login_wrapped_cmd])
        return _wrap_with_multiplexer(cmd)
    else:
        # Workspace initialization with failover guidance
        data_dir = env_config.DATA_DIR
        work_dir = os.path.join(data_dir, "workspace")
        quoted_work_dir = shlex.quote(work_dir)
        setup_cmd = f"mkdir -p {quoted_work_dir} 2>/dev/null || {{ "
        setup_cmd += "printf '\\r\\n\\033[1;33mWARNING: Persistence volume not found at /data.\\033[0m\\r\\n'; "
        setup_cmd += "printf 'To enable persistence and prevent data loss, mount a volume:\\r\\n\\r\\n'; "
        setup_cmd += "printf '\\033[1;34mDocker Compose:\\033[0m\\r\\n  volumes:\\r\\n    - data:/data\\r\\n\\r\\n'; "
        setup_cmd += "printf '\\033[1;34mDocker CLI:\\033[0m\\r\\n  docker run -v gemini_data:/data ...\\r\\n\\r\\n'; "
        setup_cmd += "sleep 10; }; "
        setup_cmd += f"cd {quoted_work_dir} 2>/dev/null || cd /tmp; "
        
        # Use shell to ensure gemini is found in PATH and handled correctly
        gemini_cmd = shlex.quote(gemini_bin)
        if resume is True or str(resume).lower() == 'true':
            gemini_cmd += " -r"
        elif str(resume).lower() == 'new':
            pass # Just run gemini without -r to start a fresh session
        elif resume and str(resume).lower() != 'false':
            gemini_cmd += f" -r {shlex.quote(str(resume))}"
        cmd = ['/bin/sh', '-c', f"{setup_cmd} exec {gemini_cmd}"]
        return _wrap_with_multiplexer(cmd)