import os
import uuid
import eventlet
import logging
from src.services.session_store import session_manager
from src.services.terminal_service import TerminalService

logger = logging.getLogger(__name__)


class AutomationBridge:
    @staticmethod
    def is_host_idle(target_host_id: str) -> bool:
        """
        Check if a target host is idle.
        target_host_id is in the format 'user@host:dir' or 'local'
        """
        if not target_host_id:
            return True

        sessions = session_manager.get_all_sessions()

        for tab_id, session in sessions.items():
            sess_target = session.ssh_target if session.ssh_target else "local"
            sess_dir = session.ssh_dir if session.ssh_dir else "~"
            sess_host_id = f"{sess_target}:{sess_dir}"

            if target_host_id == sess_host_id or target_host_id == sess_target:
                title = session.title.lower() if session.title else ""
                if "working" in title or "✋" in title:
                    return False

        return True

    @staticmethod
    def execute_task(target_host_id: str, prompt: str, prompt_context: str):
        """
        Execute a scheduled task in a new window.
        """
        ssh_target = ""
        ssh_dir = "~"
        if target_host_id and target_host_id != "local":
            parts = target_host_id.split(":", 1)
            ssh_target = parts[0]
            if len(parts) > 1:
                ssh_dir = parts[1]

        tab_id = str(uuid.uuid4())
        user_id = "automation"

        try:
            fd, pid = TerminalService.start_session(
                tab_id=tab_id,
                cols=80,
                rows=24,
                ssh_target=ssh_target,
                ssh_dir=ssh_dir,
                user_id=user_id,
                resume_task=False,
            )

            from src.gateways.terminal_socket import session_output_reader
            from src.app import socketio

            socketio.start_background_task(
                session_output_reader, tab_id, fd, pid, ssh_target, None
            )

            full_prompt = f"{prompt_context} {prompt}\n"

            # Allow a tiny bit of time for shell to spawn
            eventlet.sleep(0.5)

            os.write(fd, full_prompt.encode("utf-8"))
            logger.info(f"Automation executed task on {target_host_id} in tab {tab_id}")

        except Exception as e:
            logger.error(f"Failed to execute automation task: {e}")


automation_bridge = AutomationBridge()
