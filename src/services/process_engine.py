import os
from pathlib import Path

try:
    from config import env_config
except ImportError:
    from src.config import env_config
import re
import shlex

try:
    import eventlet.green.subprocess as subprocess
except ImportError:
    import subprocess
import time


def _get_ssh_socket_dir():
    """Get SSH socket directory, preferring XDG_RUNTIME_DIR for security.

    Uses /run/user/$UID/ (tmpfs, per-user, mode 0700 by default) when available,
    falling back to /tmp/gemini_ssh_mux for environments without it (e.g. Docker).
    """
    # Prefer XDG_RUNTIME_DIR (e.g. /run/user/1000/) — already per-user, tmpfs, 0700
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.isdir(xdg_runtime):
        candidate = Path(xdg_runtime) / "gemini_ssh_mux"
    else:
        # Fallback: try /run/user/$UID
        uid = os.getuid()
        run_user_dir = Path(f"/run/user/{uid}")
        if run_user_dir.is_dir():
            candidate = run_user_dir / "gemini_ssh_mux"
        else:
            # Final fallback for Docker/containers without /run/user
            candidate = Path("/tmp/gemini_ssh_mux")

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        os.chmod(candidate, 0o700)
    except Exception:
        # If preferred dir fails, fall back to /tmp
        candidate = Path("/tmp/gemini_ssh_mux")
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            os.chmod(candidate, 0o700)
        except Exception:
            pass

    return candidate


SSH_SOCKET_DIR = _get_ssh_socket_dir()


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
        safe_user = "".join(c for c in str(user) if c.isalnum() or c in "-_")
        safe_host = "".join(c for c in str(host) if c.isalnum() or c in "-_.")
        safe_port = "".join(c for c in str(port) if c.isdigit())
        prefix = f"{safe_user}@" if safe_user else ""
        safe_filename = f"{prefix}{safe_host}_{safe_port}.sock"
        safe_filename = os.path.basename(safe_filename)  # Prevent path traversal
        socket_path = os.path.abspath(os.path.join(str(SSH_SOCKET_DIR), safe_filename))
        if not socket_path.startswith(os.path.abspath(str(SSH_SOCKET_DIR))):
            raise ValueError("Invalid socket path")
        return socket_path

    @staticmethod
    def get_base_ssh_args(user, host, port, control_master="auto"):
        socket_path = SSHConnectionManager.get_socket_path(user, host, port)
        return [
            "-o",
            f"ControlMaster={control_master}",
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
        if not validate_ssh_target(target_str):
            raise ValueError("Invalid SSH target")

        check_cmd = [
            "ssh",
            "-O",
            "check",
            "-o",
            f"ControlPath={socket_path}",
            "--",
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
                "--",
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


def build_ssh_args(ssh_target, ssh_dir_path, control_master="auto"):
    """Builds common SSH connection arguments."""
    user, host, port = SSHConnectionManager.parse_target(ssh_target)
    SSHConnectionManager.check_and_recover_connection(user, host, port)

    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
    cmd.extend(SSHConnectionManager.get_base_ssh_args(user, host, port, control_master))

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
    """Builds a robust prefix for remote commands to ensure environment is loaded."""
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
    # We use . instead of source for POSIX compatibility
    prefix += ". ~/.profile 2>/dev/null; . ~/.bash_profile 2>/dev/null; . ~/.bashrc 2>/dev/null; "

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

        # Check for gemini before running list-sessions to avoid ugly bash errors
        remote_cmd = f"{remote_prefix} if command -v {quoted_gemini} >/dev/null 2>&1; then if command -v timeout >/dev/null 2>&1; then timeout 15 {gemini_list_cmd}; else {gemini_list_cmd}; fi; else exit 0; fi"

        # Use bash -ilc (interactive login shell) so gemini's PATH is fully loaded
        # (handles NVM, npm globals, etc.) and gemini outputs session text instead
        # of a screen-clear escape sequence (which it emits when stdin is not a TTY).
        # Use ControlMaster=no to avoid corrupting the master socket's TTY state,
        # since this fetch runs without a real PTY (stdin=DEVNULL).
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"
        cmd = build_ssh_args(ssh_target, ssh_dir_path, control_master="no")

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
        # In fake/test mode, we don't cd to workspace because the mock bin is often a relative path
        if os.path.exists(work_dir) and not os.environ.get("GEMWEBUI_HARNESS"):
            cmd = [
                "/bin/sh",
                "-c",
                f"cd {shlex.quote(work_dir)} && exec {shlex.quote(gemini_bin)} --list-sessions",
            ]
        else:
            cmd = [gemini_bin, "--list-sessions"]

    try:
        # Use a real timeout on subprocess.run to ensure we never block the main loop
        # even if the shell-level timeout fails or the process hangs during setup.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # Ensure it doesn't receive signals from parent
        )
        # Suppress auth errors from the CLI - just show as "no sessions"
        if result.returncode != 0 and (
            "Please set an Auth method" in result.stderr
            or "GEMINI_API_KEY" in result.stderr
        ):
            return {"output": "", "error": None, "timestamp": time.time()}
        return {
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "timestamp": time.time(),
        }
    except subprocess.TimeoutExpired:
        return {
            "error": "Could not establish connection (timed out)",
            "timestamp": time.time(),
        }
    except Exception:
        return {"error": "Connection failed", "timestamp": time.time()}


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
            pass  # Start a fresh session with no -r flag; JS predicts the ID for future reconnects
        elif resume and str(resume).lower() != "false":
            gemini_base_cmd += f" -r {shlex.quote(str(resume))}"

        remote_prefix = get_remote_command_prefix(
            ssh_dir, gemini_bin, env_vars=env_vars
        )

        # Smart command construction: check for gemini, drop to shell if missing
        remote_cmd = f"{remote_prefix} "
        remote_cmd += f"if command -v {quoted_gemini} >/dev/null 2>&1; then "

        if "-r" in gemini_base_cmd:
            remote_cmd += f"{gemini_base_cmd}; "
            remote_cmd += "if [ $? -ne 0 ]; then "
            remote_cmd += "printf '\\r\\n\\033[1;33mResume failed, starting new session...\\033[0m\\r\\n'; "
            remote_cmd += f"{quoted_gemini}; "
            remote_cmd += "if [ $? -ne 0 ]; then "
            remote_cmd += "printf '\\r\\n\\033[1;31mError: gemini failed, falling back to shell.\\033[0m\\r\\n'; "
            remote_cmd += "exec ${SHELL:-/bin/sh}; "
            remote_cmd += "fi; "
            remote_cmd += "fi; "
        else:
            remote_cmd += f"{gemini_base_cmd}; "
            remote_cmd += "if [ $? -ne 0 ]; then "
            remote_cmd += "printf '\\r\\n\\033[1;31mError: gemini failed, falling back to shell.\\033[0m\\r\\n'; "
            remote_cmd += "exec ${SHELL:-/bin/sh}; "
            remote_cmd += "fi; "

        remote_cmd += "else "
        remote_cmd += "printf '\\r\\n\\033[1;31mError: gemini CLI not found on remote host.\\033[0m\\r\\n'; "
        remote_cmd += "printf 'Please install it from: \\033[1;34mhttps://geminicli.com/\\033[0m\\r\\n\\r\\n'; "
        remote_cmd += "exec ${SHELL:-/bin/sh}; "
        remote_cmd += "fi"

        # Use a login shell to ensure PATH is correctly set up (e.g. for NVM, npm globals)
        # This is safe because we are using 'ssh -t' which provides a TTY.
        login_wrapped_remote_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"

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

        clean_target = ssh_target
        if ":" in ssh_target:
            parts = ssh_target.rsplit(":", 1)
            if parts[1].isdigit():
                clean_target = parts[0]
                cmd.extend(["-p", parts[1]])

        cmd.extend(["--", clean_target, login_wrapped_remote_cmd])
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
        if not os.environ.get("GEMINI_WEBUI_HARNESS_ID"):
            setup_cmd += "sleep 10; "
        setup_cmd += "}; "
        setup_cmd += f"cd {quoted_work_dir} 2>/dev/null || cd /tmp; "

        # Use shell to ensure gemini is found in PATH and handled correctly
        # Split gemini_bin in case it contains arguments (e.g. "python3 mock.py")
        bin_parts = shlex.split(gemini_bin)
        gemini_executable = shlex.quote(bin_parts[0])
        gemini_args = " ".join(
            shlex.quote(arg) for i, arg in enumerate(bin_parts) if i > 0
        )
        gemini_cmd = f"{gemini_executable} {gemini_args}".strip()

        if resume is True or str(resume).lower() == "true":
            gemini_cmd += " -r"
        elif str(resume).lower() == "new":
            pass  # Start a fresh session with no -r flag; JS predicts the ID for future reconnects
        elif resume and str(resume).lower() != "false":
            gemini_cmd += f" -r {shlex.quote(str(resume))}"

        local_cmd = f"if command -v {gemini_executable} >/dev/null 2>&1; then "
        if "-r" in gemini_cmd:
            local_cmd += f"{gemini_cmd}; "
            local_cmd += "if [ $? -ne 0 ]; then "
            local_cmd += "printf '\\r\\n\\033[1;33mResume failed, starting new session...\\033[0m\\r\\n'; "
            local_cmd += f"{gemini_executable} {gemini_args}; "
            local_cmd += "if [ $? -ne 0 ]; then "
            local_cmd += "printf '\\r\\n\\033[1;31mError: gemini failed, falling back to shell.\\033[0m\\r\\n'; "
            local_cmd += "exec ${SHELL:-/bin/sh}; "
            local_cmd += "fi; "
            local_cmd += "fi; "
        else:
            local_cmd += f"{gemini_cmd}; "
            local_cmd += "if [ $? -ne 0 ]; then "
            local_cmd += "printf '\\r\\n\\033[1;31mError: gemini failed, falling back to shell.\\033[0m\\r\\n'; "
            local_cmd += "exec ${SHELL:-/bin/sh}; "
            local_cmd += "fi; "
        local_cmd += "else "
        local_cmd += (
            "printf '\\r\\n\\033[1;31mError: gemini CLI not found.\\033[0m\\r\\n'; "
        )
        local_cmd += "printf 'Please install it from: \\033[1;34mhttps://geminicli.com/\\033[0m\\r\\n\\r\\n'; "
        local_cmd += "exec ${SHELL:-/bin/sh}; "
        local_cmd += "fi"

        cmd = ["/bin/sh", "-c", f"{setup_cmd} {local_cmd}"]
        return _wrap_with_multiplexer(cmd)


import os
import signal
from src.shared_state import abandoned_pids, abandoned_pids_lock


def kill_and_reap(pid):
    """Kills a process and its entire group, then reaps the zombie immediately."""
    if pid is None:
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    try:
        res = os.waitpid(pid, os.WNOHANG)
        if res == (0, 0):
            with abandoned_pids_lock:
                abandoned_pids.add(pid)
    except ChildProcessError:
        pass
    except OSError:
        pass
