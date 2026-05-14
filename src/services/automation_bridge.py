import os
import uuid
import eventlet
import logging
import select
from src.services.session_store import session_manager
from src.services.terminal_service import TerminalService
from src.services.schedule_manager import schedule_manager
from src.infrastructure.process_manager import kill_and_reap

logger = logging.getLogger(__name__)


def automation_output_reader(tab_id, job_id, fd):
    """Background task to read output from a specific session's PTY and capture automation results."""
    from src.app import socketio

    session_obj = session_manager.get_session(tab_id)
    if not session_obj:
        return

    max_read_bytes = 1024 * 20
    decoder = session_obj.decoder

    output_buffer = []
    started = False
    finished = False
    exit_code = None

    try:
        # Update job to running
        with schedule_manager._get_connection() as conn:
            conn.execute(
                "UPDATE automation_jobs SET status = 'running' WHERE id = ?", (job_id,)
            )
            conn.commit()

        while getattr(session_obj, "active", True):
            try:
                (data_ready, _, _) = select.select([fd], [], [], 0.5)
                if not getattr(session_obj, "active", True):
                    break
                if data_ready:
                    output = os.read(fd, max_read_bytes)
                    if not output:  # EOF
                        break

                    decoded_output = decoder.decode(output)
                    if decoded_output:
                        # Append to session buffer for real-time viewing if a client connects
                        session_obj.append_buffer(decoded_output)
                        socketio.emit(
                            "pty-output", {"output": decoded_output}, room=tab_id
                        )

                        # Accumulate in our local buffer for parsing
                        output_buffer.append(decoded_output)
                        full_str = "".join(output_buffer)

                        # Check for markers
                        if "___GAB_START___" in full_str:
                            started = True

                        if started and "___GAB_END___" in full_str:
                            finished = True
                            # Parse exit code
                            parts = full_str.split("___GAB_END___")
                            after_end = parts[1].strip().split()
                            if after_end:
                                try:
                                    exit_code = int(after_end[0])
                                except ValueError:
                                    pass
                            break

                socketio.sleep(0.01)
            except (OSError, IOError):
                break
    except Exception as e:
        logger.error(f"Error in automation output reader for {tab_id}: {e}")
    finally:
        logger.info(f"Automation reader for {tab_id} finished")
        status = "completed" if finished else "failed"
        if not finished:
            exit_code = -1

        full_output = "".join(output_buffer)
        # Try to extract just the payload
        if started and finished:
            try:
                payload = full_output.split("___GAB_START___")[1].split(
                    "___GAB_END___"
                )[0]
                full_output = payload.strip()
            except IndexError:
                pass

        with schedule_manager._get_connection() as conn:
            conn.execute(
                "UPDATE automation_jobs SET status = ?, output = ?, exit_code = ? WHERE id = ?",
                (status, full_output, exit_code, job_id),
            )
            conn.commit()

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

        tab_id = str(uuid.uuid4())
        user_id = "automation"

        job_id = schedule_manager.add_job(schedule_id, "queued")

        try:
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
            )

            if err or not session_obj:
                raise Exception(err or "Failed to create session")

            # Register session so get_session works
            session_manager.reclaim_session(tab_id, None, user_id)

            from src.app import socketio

            # Start our custom reader
            socketio.start_background_task(
                automation_output_reader, tab_id, job_id, session_obj.fd
            )

            script = f"echo ___GAB_START___; {prompt_context} {prompt}; echo ___GAB_END___ $?\n"

            # Allow a tiny bit of time for shell to spawn
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
