import os
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

def fetch_sessions_for_host(host, ssh_dir_path, gemini_bin='gemini'):
    """Internal helper to fetch sessions for a host config."""
    ssh_target = host.get('target')
    ssh_dir = host.get('dir')
    cmd = []
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return {"error": "Invalid SSH target format", "timestamp": time.time()}
            
        gemini_list_cmd = f"{gemini_bin} --list-sessions" if gemini_bin != 'gemini' else "gemini --list-sessions"
        remote_env = "export TERM=xterm-256color; export COLORTERM=truecolor; export FORCE_COLOR=3; "
        if ssh_dir and ssh_dir != "~":
            # Handle tilde expansion for remote shell
            if ssh_dir.startswith('~'):
                suffix = ssh_dir[1:]
                remote_cmd = f"{remote_env} cd ~{shlex.quote(suffix)} && {gemini_list_cmd}"
            else:
                remote_cmd = f"{remote_env} cd {shlex.quote(ssh_dir)} && {gemini_list_cmd}"
        else:
            remote_cmd = f"{remote_env} {gemini_list_cmd}"
            
        login_wrapped_cmd = f"bash -l -c {shlex.quote(remote_cmd)}"
            
        cmd = build_ssh_args(ssh_target, ssh_dir_path)
        cmd.extend(['--', ssh_target, login_wrapped_cmd])
    else:
        # Use workspace for local session listing to match startSession
        work_dir = "/data/workspace"
        if os.path.exists(work_dir):
            cmd = ['/bin/sh', '-c', f"cd {work_dir} && {gemini_bin} --list-sessions"]
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
    except Exception as e:
        return {"error": "Connection failed", "timestamp": time.time()}

def _wrap_with_multiplexer(cmd):
    """Wraps the terminal command in a multiplexer (tmux or dtach) to prevent visual corruption on detach/re-attach."""
    import shutil
    import uuid
    session_id = f"gemini_{uuid.uuid4().hex[:8]}"
    
    if shutil.which('tmux'):
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        return ['tmux', 'new-session', '-A', '-s', session_id, cmd_str]
    elif shutil.which('dtach'):
        return ['dtach', '-A', f"/tmp/{session_id}", '-r', 'winch'] + cmd
    
    return cmd

def build_terminal_command(ssh_target, ssh_dir, resume, ssh_dir_path, gemini_bin='gemini'):
    """Builds the shell/ssh command array for os.execvp when starting a PTY."""
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return None # Invalid target
            
        gemini_base_cmd = gemini_bin
        if resume is True or str(resume).lower() == 'true':
            gemini_base_cmd += " -r"
        elif resume and str(resume).lower() != 'false':
            gemini_base_cmd += f" -r {resume}"
        
        # Export color env vars remotely
        remote_env = "export TERM=xterm-256color; export COLORTERM=truecolor; export FORCE_COLOR=3; "
        
        # Smart command construction: check for gemini, drop to shell if missing
        remote_cmd = f"{remote_env} if command -v {gemini_bin} >/dev/null 2>&1; then "
        if ssh_dir and ssh_dir != "~":
            if ssh_dir.startswith('~'):
                suffix = ssh_dir[1:]
                remote_cmd += f"cd ~{shlex.quote(suffix)} && {gemini_base_cmd}; "
            else:
                remote_cmd += f"cd {shlex.quote(ssh_dir)} && {gemini_base_cmd}; "
        else:
            remote_cmd += f"{gemini_base_cmd}; "
        
        remote_cmd += "else "
        remote_cmd += "printf '\\r\\n\\033[1;31mError: gemini CLI not found on remote host.\\033[0m\\r\\n'; "
        remote_cmd += "printf 'Please install it from: \\033[1;34mhttps://geminicli.com/\\033[0m\\r\\n\\r\\n'; "
        remote_cmd += "exec $SHELL; "
        remote_cmd += "fi"
        
        # Wrap in login shell to ensure .profile/.bash_profile PATH is loaded
        login_wrapped_cmd = f"bash -l -c {shlex.quote(remote_cmd)}"
            
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
            '--', ssh_target, login_wrapped_cmd
        ])
        return _wrap_with_multiplexer(cmd)
    else:
        # Workspace initialization with failover guidance
        work_dir = "/data/workspace"
        setup_cmd = f"mkdir -p {work_dir} 2>/dev/null || {{ "
        setup_cmd += "printf '\\r\\n\\033[1;33mWARNING: Persistence volume not found at /data.\\033[0m\\r\\n'; "
        setup_cmd += "printf 'To enable persistence and prevent data loss, mount a volume:\\r\\n\\r\\n'; "
        setup_cmd += "printf '\\033[1;34mDocker Compose:\\033[0m\\r\\n  volumes:\\r\\n    - data:/data\\r\\n\\r\\n'; "
        setup_cmd += "printf '\\033[1;34mDocker CLI:\\033[0m\\r\\n  docker run -v gemini_data:/data ...\\r\\n\\r\\n'; "
        setup_cmd += "sleep 10; }; "
        setup_cmd += f"cd {work_dir} 2>/dev/null || cd /tmp; "
        
        # Use shell to ensure gemini is found in PATH and handled correctly
        gemini_cmd = gemini_bin
        if resume is True or str(resume).lower() == 'true':
            gemini_cmd += " -r"
        elif resume and str(resume).lower() != 'false':
            gemini_cmd += f" -r {resume}"
        cmd = ['/bin/sh', '-c', f"{setup_cmd} exec {gemini_cmd}"]
        return _wrap_with_multiplexer(cmd)