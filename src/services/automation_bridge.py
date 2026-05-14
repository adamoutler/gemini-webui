import os
import uuid
import eventlet
import logging
import time
import re
from src.services.session_store import session_manager
from src.services.terminal_service import TerminalService
from src.services.schedule_manager import schedule_manager
from src.infrastructure.process_manager import kill_and_reap

logger = logging.getLogger(__name__)


def automation_output_reader(tab_id, job_id, start_buffer_len):
    """Background task to monitor session_obj.buffer for automation results."""
    from src.app import socketio

    session_obj = session_manager.get_session(tab_id)
    if not session_obj:
        return

    output_buffer = []
    started = False
    finished = False
    exit_code = None

    start_marker = f"___GAB_START_{job_id}___"
    end_marker = f"___GAB_END_{job_id}___"

    try:
        with schedule_manager._get_connection() as conn:
            conn.execute(
                "UPDATE automation_jobs SET status = 'running' WHERE id = ?", (job_id,)
            )
            conn.commit()

        # Wait for the marker in the buffer
        while getattr(session_obj, "active", True):
            buffer_list = list(session_obj.buffer)
            new_data = "".join(buffer_list)

            # Strip ANSI codes for regex matching
            ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
            clean_data = ansi_escape.sub("", new_data)

            if start_marker in clean_data:
                started = True

            # Look for the actual executed end marker, which has digits after it
            end_match = re.search(f"{end_marker}\\s+(\\d+)", clean_data)

            if started and end_match:
                finished = True
                exit_code = int(end_match.group(1))
                output_buffer.append(new_data)
                break

            eventlet.sleep(0.5)

    except Exception as e:
        logger.error(f"Error in automation output reader for {tab_id}: {e}")
    finally:
        logger.info(f"Automation reader for {tab_id} finished")
        status = "completed" if finished else "failed"
        if not finished:
            exit_code = -1

        full_output = "".join(output_buffer) if output_buffer else ""

        if started and finished:
            try:
                # Extract the payload between the LAST start and LAST end marker
                payload = full_output.rsplit(start_marker, 1)[1].rsplit(end_marker, 1)[
                    0
                ]
                full_output = payload.strip()
            except IndexError:
                pass

        with schedule_manager._get_connection() as conn:
            conn.execute(
                "UPDATE automation_jobs SET status = ?, output = ?, exit_code = ? WHERE id = ?",
                (status, full_output, exit_code, job_id),
            )
            conn.commit()

        socketio.emit("lock_state_changed", {"locked": False}, room=tab_id)

        # Do NOT kill the session if we hijacked an existing one.
        if getattr(session_obj, "user_id", None) == "automation":
            if getattr(session_obj, "active", True):
                session_manager.remove_session(tab_id)
                if session_obj and session_obj.pid is not None:
                    kill_and_reap(session_obj.pid)


class AutomationBridge:
    @staticmethod
    def is_host_idle(target_host_id: str) -> bool:
        if not target_host_id:
            return True

        sessions = session_manager.get_all_sessions()
        now = time.time()

        for session in sessions:
            if not getattr(session, "active", False):
                continue
            sess_target = session.ssh_target if session.ssh_target else "local"
            sess_dir = session.ssh_dir if session.ssh_dir else "~"
            sess_host_id = f"{sess_target}:{sess_dir}"

            if target_host_id == sess_host_id or target_host_id == sess_target:
                title = session.title.lower() if session.title else ""
                if "working" in title or "✋" in title:
                    return False

                # Check for silence (no output for 500ms)
                if session.last_seen and (now - session.last_seen < 0.5):
                    return False

                # Check for shell prompt patterns at the end of the buffer
                if session.buffer:
                    last_line = session.buffer[-1].strip()
                    if not re.search(r"[$#>%]\s*$", last_line):
                        return False

        return True

    @staticmethod
    def execute_task(
        target_host_id: str, prompt: str, prompt_context: str, schedule_id: str = None
    ):
        ssh_target = ""
        ssh_dir = "~"
        if target_host_id and target_host_id != "local":
            parts = target_host_id.split(":", 1)
            ssh_target = parts[0]
            if len(parts) > 1:
                ssh_dir = parts[1]

        user_id = "automation"
        job_id = schedule_manager.add_job(schedule_id, "queued")

        # Find an existing session
        sessions = session_manager.get_all_sessions()
        target_session = None
        for session in sessions:
            if not getattr(session, "active", False):
                continue
            sess_target = session.ssh_target if session.ssh_target else "local"
            sess_dir = session.ssh_dir if session.ssh_dir else "~"
            sess_host_id = f"{sess_target}:{sess_dir}"
            if target_host_id == sess_host_id or target_host_id == sess_target:
                target_session = session
                break

        try:
            from src.app import socketio

            if target_session:
                session_obj = target_session
                tab_id = session_obj.tab_id
                logger.info(f"Injecting automation task into existing session {tab_id}")
            else:
                tab_id = str(uuid.uuid4())
                session_obj, err = TerminalService.start_session(
                    tab_id=tab_id,
                    user_id=user_id,
                    ssh_target=ssh_target,
                    ssh_dir=ssh_dir,
                    resume=False,
                    cols=80,
                    rows=24,
                    env_vars={},
                    title="Automation Job",
                    executable_override="bash --noprofile --norc",
                )
                if err or not session_obj:
                    raise Exception(err or "Failed to create session")
                session_manager.reclaim_session(tab_id, None, user_id)

                from src.gateways.terminal_socket import session_output_reader

                socketio.start_background_task(session_output_reader, tab_id)

            socketio.emit("lock_state_changed", {"locked": True}, room=tab_id)
            start_buffer_len = len(session_obj.buffer)

            # Start our custom reader monitoring the buffer
            socketio.start_background_task(
                automation_output_reader, tab_id, job_id, start_buffer_len
            )

            # We use a unique marker per job to avoid conflicts with echoes
            safe_context = prompt_context.replace('"', '\\"')
            start_marker = f"___GAB_START_{job_id}___"
            end_marker = f"___GAB_END_{job_id}___"
            script = f'echo {start_marker}; echo "{safe_context}"; {prompt}; echo {end_marker} $?\n'

            eventlet.sleep(0.5)

            os.write(session_obj.fd, script.encode("utf-8"))
            logger.info(f"Automation executed task on {target_host_id} in tab {tab_id}")

        except Exception as e:
            logger.error(f"Failed to execute automation task: {e}")
            with schedule_manager._get_connection() as conn:
                conn.execute(
                    "UPDATE automation_jobs SET status = 'failed', output = ? WHERE id = ?",
                    (str(e), job_id),
                )
                conn.commit()


automation_bridge = AutomationBridge()
