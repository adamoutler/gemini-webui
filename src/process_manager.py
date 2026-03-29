import os
from pathlib import Path

try:
    from config import env_config
except ImportError:
    from src.config import env_config
import re
import shlex
import subprocess
import time

SSH_SOCKET_DIR = Path("/tmp/gemini_ssh_mux")
try:
    SSH_SOCKET_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SSH_SOCKET_DIR, 0o700)
except Exception:
    pass


class SSHConnectionManager:
    @staticmethod
    def parse_target(target):
        user = ""
        port = 22
        host = target
        if ":" in host:
            parts = host.rsplit(":", 1)
            if parts[1].isdigit():
                host = parts[0]
                port = int(parts[1])
        if "@" in host:
            user, host = host.split("@", 1)
        return user, host, port

    @staticmethod
    def get_socket_path(user, host, port):
        safe_user = "".join(c for c in user if c.isalnum() or c in "-_")
        safe_host = "".join(c for c in host if c.isalnum() or c in "-_.")
        prefix = f"{safe_user}@" if safe_user else ""
        return str(SSH_SOCKET_DIR / f"{prefix}{safe_host}:{port}.sock")

    @staticmethod
    def get_base_ssh_args(user, host, port):
        socket_path = SSHConnectionManager.get_socket_path(user, host, port)
        return [
            "-o",
            "ControlMaster=auto",
            "-o",
            f"ControlPath={socket_path}",
            "-o",
            "ControlPersist=10m",
        ]

    @staticmethod
    def check_and_recover_connection(user, host, port):
        socket_path = SSHConnectionManager.get_socket_path(user, host, port)
        if not os.path.exists(socket_path):
            return

        target_str = f"{user}@{host}" if user else host

        check_cmd = [
            "ssh",
            "-O",
            "check",
            "-o",
            f"ControlPath={socket_path}",
            target_str,
        ]
        try:
            result = subprocess.run(
                check_cmd, capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                raise Exception("Connection dead")
        except (subprocess.TimeoutExpired, Exception):
            exit_cmd = [
                "ssh",
                "-O",
                "exit",
                "-o",
                f"ControlPath={socket_path}",
                target_str,
            ]
            try:
                subprocess.run(exit_cmd, capture_output=True, timeout=5)
            except Exception:
                pass
            if os.path.exists(socket_path):
                try:
                    os.remove(socket_path)
                except OSError:
                    pass


def validate_ssh_target(target):
    """Ensure SSH target is in a safe format (user@host, host, or host:port)."""
    if not target:
        return False
    # Allow alphanumeric, dots, hyphens, optional user@, and optional :port
    return bool(re.match(r"^([a-zA-Z0-9.-]+@)?[a-zA-Z0-9.-]+(:[0-9]+)?$", target))


def build_ssh_args(ssh_target, ssh_dir_path):
    """Builds common SSH connection arguments."""
    user, host, port = SSHConnectionManager.parse_target(ssh_target)
    SSHConnectionManager.check_and_recover_connection(user, host, port)

    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
    cmd.extend(SSHConnectionManager.get_base_ssh_args(user, host, port))

    known_hosts_path = os.path.join(ssh_dir_path, "known_hosts")
    if not os.access(ssh_dir_path, os.W_OK) and not os.access(
        known_hosts_path, os.W_OK
    ):
        known_hosts_path = "/dev/null"
    cmd.extend(["-o", f"UserKnownHostsFile={known_hosts_path}"])

    if os.path.exists(ssh_dir_path):
        for f in os.listdir(ssh_dir_path):
            if (
                os.path.isfile(os.path.join(ssh_dir_path, f))
                and f not in ["config", "known_hosts"]
                and not f.endswith(".pub")
            ):
                cmd.extend(["-i", os.path.join(ssh_dir_path, f)])
    return cmd


def get_remote_command_prefix(ssh_dir, gemini_bin="gemini", env_vars=None):
    """Builds a robust prefix for remote commands to ensure PATH and environment are loaded."""
    # Common color and path exports
    prefix = 'export PATH="$PATH:$HOME/.local/bin:$HOME/bin"; '
    prefix += (
        "export TERM=xterm-256color; export COLORTERM=truecolor; export FORCE_COLOR=3; "
    )

    if env_vars and isinstance(env_vars, dict):
        for k, v in env_vars.items():
            if isinstance(k, str) and isinstance(v, str):
                prefix += f"export {k}={shlex.quote(v)}; "

    # Source profiles quietly to populate PATH (e.g. npm globals, nvm, etc.)
    prefix += "source ~/.profile 2>/dev/null; source ~/.bash_profile 2>/dev/null; source ~/.bashrc 2>/dev/null; "
    if ssh_dir and ssh_dir != "~":
        if ssh_dir.startswith("~"):
            suffix = ssh_dir[1:]
            prefix += f"cd ~{shlex.quote(suffix)} 2>/dev/null || cd ~; "
        else:
            prefix += f"cd {shlex.quote(ssh_dir)} 2>/dev/null || cd ~; "

    return prefix


def fetch_sessions_for_host(host, ssh_dir_path, gemini_bin="gemini"):
    """Internal helper to fetch sessions for a host config."""
    ssh_target = host.get("target")
    ssh_dir = host.get("dir")
    env_vars = host.get("env_vars")
    cmd = []
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return {"error": "Invalid SSH target format", "timestamp": time.time()}

        quoted_gemini = shlex.quote(gemini_bin)
        gemini_list_cmd = f"{quoted_gemini} --list-sessions"
        remote_prefix = get_remote_command_prefix(
            ssh_dir, gemini_bin, env_vars=env_vars
        )

        # Check for gemini before running list-sessions to avoid ugly bash errors.
        # We use 'exec' so the timeout/gemini process replaces bash and receives signals directly.
        # We use 'timeout -k 2 10' so the remote host aggressively kills hung CLI processes 
        # BEFORE the local Python subprocess.run(timeout=15) kills the SSH client.
        remote_cmd = f"{remote_prefix} if command -v {quoted_gemini} >/dev/null 2>&1; then if command -v timeout >/dev/null 2>&1; then exec timeout -k 2 10 {gemini_list_cmd}; else exec {gemini_list_cmd}; fi; else exit 0; fi"

        # Wrap in login shell to ensure .profile/.bash_profile PATH is loaded (e.g. for NVM)
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"

        cmd = build_ssh_args(ssh_target, ssh_dir_path)

        clean_target = ssh_target
        if ":" in ssh_target:
            parts = ssh_target.rsplit(":", 1)
            if parts[1].isdigit():
                clean_target = parts[0]
                cmd.extend(["-p", parts[1]])

        cmd.extend(["--", clean_target, login_wrapped_cmd])
    else:
        # Use workspace for local session listing to match startSession
        data_dir = env_config.DATA_DIR
        work_dir = os.path.join(data_dir, "workspace")
        if os.path.exists(work_dir):
            cmd = [
                "/bin/sh",
                "-c",
                f"cd {shlex.quote(work_dir)} && exec {shlex.quote(gemini_bin)} --list-sessions",
            ]
        else:
            cmd = [gemini_bin, "--list-sessions"]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid,
        )
        try:
            stdout, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            import signal
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
            return {
                "error": "Could not establish connection (timed out)",
                "timestamp": time.time(),
            }
        except Exception as e:
            import signal
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
            return {"error": f"Connection failed: {e}", "timestamp": time.time()}

        # Suppress auth errors from the CLI - just show as "no sessions"
        if proc.returncode != 0 and (
            "Please set an Auth method" in stderr
            or "GEMINI_API_KEY" in stderr
        ):
            return {"output": "", "error": None, "timestamp": time.time()}
        return {
            "output": stdout,
            "error": stderr if proc.returncode != 0 else None,
            "timestamp": time.time(),
        }
    except Exception as e:
        return {"error": f"Process launch failed: {e}", "timestamp": time.time()}


def _wrap_with_multiplexer(cmd):
    """Wraps the terminal command in a multiplexer (tmux or dtach) to prevent visual corruption on detach/re-attach."""
    if env_config.SKIP_MULTIPLEXER:
        return cmd

    import shutil
    import uuid

    session_id = f"gemini_{uuid.uuid4().hex[:8]}"

    if shutil.which("tmux"):
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        return ["tmux", "new-session", "-A", "-s", session_id, cmd_str]
    elif shutil.which("dtach"):
        return ["dtach", "-A", f"/tmp/{session_id}", "-r", "winch"] + cmd

    return cmd


def build_terminal_command(
    ssh_target,
    ssh_dir,
    resume,
    ssh_dir_path,
    gemini_bin="gemini",
    env_vars=None,
    is_fake=False,
    executable_override=None,
):
    """Builds the shell/ssh command array for os.execvp when starting a PTY."""
    if executable_override:
        return shlex.split(executable_override)
    if is_fake:
        cmd = shlex.split(gemini_bin)
        return cmd

    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return None  # Invalid target

        user, host, port = SSHConnectionManager.parse_target(ssh_target)
        SSHConnectionManager.check_and_recover_connection(user, host, port)

        quoted_gemini = shlex.quote(gemini_bin)
        gemini_base_cmd = quoted_gemini
        if resume is True or str(resume).lower() == "true":
            gemini_base_cmd += " -r"
        elif str(resume).lower() == "new":
            pass  # Just run gemini without -r to start a fresh session
        elif resume and str(resume).lower() != "false":
            gemini_base_cmd += f" -r {shlex.quote(str(resume))}"

        remote_prefix = get_remote_command_prefix(
            ssh_dir, gemini_bin, env_vars=env_vars
        )

        # Smart command construction: check for gemini, drop to shell if missing
        remote_cmd = (
            f"{remote_prefix} if command -v {quoted_gemini} >/dev/null 2>&1; then "
        )
        remote_cmd += f"{gemini_base_cmd}; "
        remote_cmd += "else "
        remote_cmd += "printf '\\r\\n\\033[1;31mError: gemini CLI not found on remote host.\\033[0m\\r\\n'; "
        remote_cmd += "printf 'Please install it from: \\033[1;34mhttps://geminicli.com/\\033[0m\\r\\n\\r\\n'; "
        remote_cmd += "exec $SHELL; "
        remote_cmd += "fi"

        # Use remote_cmd directly. SSH will execute it in the remote user's default shell.
        # The remote_prefix ensures that PATH is set and profiles are sourced.
        cmd = ["ssh", "-t"]
        cmd.extend(SSHConnectionManager.get_base_ssh_args(user, host, port))

        known_hosts_path = os.path.join(ssh_dir_path, "known_hosts")
        if not os.access(ssh_dir_path, os.W_OK) and not os.access(
            known_hosts_path, os.W_OK
        ):
            known_hosts_path = "/dev/null"
        cmd.extend(["-o", f"UserKnownHostsFile={known_hosts_path}"])

        if os.path.exists(ssh_dir_path):
            for f in os.listdir(ssh_dir_path):
                if (
                    os.path.isfile(os.path.join(ssh_dir_path, f))
                    and f not in ["config", "known_hosts"]
                    and not f.endswith(".pub")
                ):
                    cmd.extend(["-i", os.path.join(ssh_dir_path, f)])
        cmd.extend(
            [
                "-o",
                "PreferredAuthentications=publickey,password",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ServerAliveInterval=60",
                "-o",
                "ServerAliveCountMax=120",  # Allow up to 2 hours of silence
            ]
        )

        # Wrap in login shell to ensure .profile/.bash_profile PATH is loaded (e.g. for NVM)
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"

        clean_target = ssh_target
        if ":" in ssh_target:
            parts = ssh_target.rsplit(":", 1)
            if parts[1].isdigit():
                clean_target = parts[0]
                cmd.extend(["-p", parts[1]])

        cmd.extend(["--", clean_target, login_wrapped_cmd])
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
        if resume is True or str(resume).lower() == "true":
            gemini_cmd += " -r"
        elif str(resume).lower() == "new":
            pass  # Just run gemini without -r to start a fresh session
        elif resume and str(resume).lower() != "false":
            gemini_cmd += f" -r {shlex.quote(str(resume))}"
        cmd = ["/bin/sh", "-c", f"{setup_cmd} exec {gemini_cmd}"]
        return _wrap_with_multiplexer(cmd)
