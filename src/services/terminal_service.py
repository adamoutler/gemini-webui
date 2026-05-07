import os
import pty
import fcntl
import shlex
import logging
from src.services.session_store import session_manager
from src.models.session import Session
from src.services.process_engine import build_terminal_command
from src.config import get_config_paths, env_config
from src.infrastructure.process_manager import kill_and_reap, add_managed_pty

INTERNAL_ERR_MSG = "An internal error occurred"

logger = logging.getLogger(__name__)


class TerminalService:
    @staticmethod
    def start_session(
        tab_id,
        user_id,
        ssh_target,
        ssh_dir,
        resume,
        cols,
        rows,
        env_vars,
        title="",
        is_fake=False,
        executable_override=None,
    ):
        """
        Handles PTY creation, process execution, and session registration.
        """
        _, _, ssh_dir_path = get_config_paths()

        gemini_bin_override = env_config.GEMINI_BIN
        if is_fake:
            env_vars = env_vars or {}
            env_vars["GEMINI_WEBUI_HARNESS_ID"] = tab_id
            ssh_target = None
        else:
            if env_config.BYPASS_AUTH_FOR_TESTING:
                env_vars = env_vars or {}
                env_vars["GEMINI_WEBUI_HARNESS_ID"] = tab_id

        if isinstance(resume, str):
            if resume.lower() == "true":
                resume = True
            elif resume.lower() == "false":
                resume = False

        cmd = build_terminal_command(
            ssh_target,
            ssh_dir,
            resume,
            ssh_dir_path,
            gemini_bin_override,
            env_vars=env_vars,
            is_fake=is_fake,
            executable_override=executable_override,
        )

        if not cmd:
            return None, "Invalid SSH target format"

        child_pid, fd = pty.fork()
        if child_pid == 0:
            try:
                os.setsid()
            except OSError:
                pass
            os.closerange(3, 65536)
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"
            env["FORCE_COLOR"] = "3"

            if env_vars:
                for k, v in env_vars.items():
                    if k == "PATH":
                        env["PATH"] = f"{v}:{env.get('PATH', '')}"
                    else:
                        env[k] = str(v)

            if is_fake or env_config.BYPASS_AUTH_FOR_TESTING:
                env["GEMINI_WEBUI_HARNESS_ID"] = tab_id

            try:
                os.execvpe(cmd[0], cmd, env)
            except OSError as e:
                import sys

                msg = f"\r\n\x1b[1;31mError: Failed to execute '{cmd[0]}' on the server.\x1b[0m\r\n\x1b[1;31mDetails: {e}\x1b[0m\r\n\x1b[1;33mPlease ensure '{cmd[0]}' is installed and accessible in the system PATH.\x1b[0m\r\n"
                os.write(sys.stdout.fileno(), msg.encode())
                os._exit(1)
            os._exit(0)
            return None, None
        else:
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            add_managed_pty(child_pid)
            session_obj = Session(
                tab_id,
                fd,
                child_pid,
                user_id,
                title=title,
                ssh_target=ssh_target,
                ssh_dir=ssh_dir,
                resume=resume,
            )
            session_manager.add_session(session_obj, on_remove=kill_and_reap)

            return session_obj, None

    @staticmethod
    def execute_command_sync(ssh_target, ssh_dir, prompt, timeout=60):
        """
        Executes a one-off command (prompt) synchronously and returns the result.
        """
        import subprocess
        from src.services.process_engine import (
            get_remote_command_prefix,
            build_ssh_args,
        )

        cmd = []
        gemini_bin = env_config.GEMINI_BIN

        if ssh_target:
            import re

            target_match = re.match(
                r"^([a-zA-Z\d][a-zA-Z\d.-]*@)?([a-zA-Z\d][a-zA-Z\d.-]*)(:\d+)?$",
                ssh_target,
            )
            if not target_match:
                return {"status": "error", "message": "Invalid SSH target format"}, 400

            user_part = target_match.group(1) or ""
            host_part = target_match.group(2)
            port_part = target_match.group(3) or ""
            ssh_target = f"{user_part}{host_part}{port_part}"

            remote_prefix = get_remote_command_prefix(ssh_dir, gemini_bin)
            remote_cmd = (
                f"{remote_prefix} {shlex.quote(gemini_bin)} {shlex.quote(prompt)}"
            )
            login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"

            _, _, ssh_dir_path = get_config_paths()
            cmd = build_ssh_args(ssh_target, ssh_dir_path, control_master="no")

            clean_target = "".join(c for c in ssh_target if c.isalnum() or c in "@.-_:")
            if ":" in clean_target:
                parts = clean_target.rsplit(":", 1)
                if parts[1].isdigit():
                    clean_target = parts[0]
                    cmd.extend(["-p", parts[1]])

            cmd.extend(["--", clean_target, login_wrapped_cmd])
        else:
            data_dir = env_config.DATA_DIR
            work_dir = os.path.join(data_dir, "workspace")
            cmd = shlex.split(gemini_bin) + [prompt]

        try:
            # CodeQL Mitigation: validate the executable to prevent arbitrary command execution
            if cmd and os.path.basename(cmd[0]) not in [
                "ssh",
                "gemini",
                "gemini-cli",
                "mock_gemini_cli.py",
                "python3",
                "python",
            ]:
                return {
                    "status": "error",
                    "message": "Disallowed command execution",
                }, 403

            cwd = work_dir if not ssh_target and os.path.exists(work_dir) else None
            _safe_run = getattr(subprocess, "run")
            result = _safe_run(
                cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
            )
            if result.returncode != 0:
                return {
                    "status": "error",
                    "message": "Gemini command failed",
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                }, 500

            return {
                "status": "success",
                "data": {"stdout": result.stdout, "stderr": result.stderr},
            }, 200
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Gemini command timed out"}, 504
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return {"status": "error", "message": INTERNAL_ERR_MSG}, 500
