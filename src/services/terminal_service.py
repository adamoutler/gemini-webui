import os
import pty
import fcntl
import threading
import shlex
import logging
from src.services.session_store import Session, session_manager
from src.services.process_engine import build_terminal_command
from src.config import get_config_paths, env_config
from src.infrastructure.process_manager import kill_and_reap, add_managed_pty

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
