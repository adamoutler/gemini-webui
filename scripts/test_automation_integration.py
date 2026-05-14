import os
import sys
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from src.services.schedule_manager import schedule_manager
from src.services.automation_scheduler import automation_scheduler
from src.services.session_store import session_manager
from src.infrastructure.process_manager import apply_subprocess_monkey_patch

apply_subprocess_monkey_patch()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_integration_test():
    logger.info("Starting Automation Integration Test...")

    # 1. Add a real session to prove idle logic
    from src.services.terminal_service import TerminalService
    import uuid

    tab_id = str(uuid.uuid4())
    session_obj, err = TerminalService.start_session(
        tab_id=tab_id,
        user_id="testuser",
        ssh_target="",
        ssh_dir="~",
        resume=False,
        cols=80,
        rows=24,
        env_vars={},
        title="Integration Test Session",
        executable_override="bash --noprofile --norc",
    )
    if err or not session_obj:
        logger.error(f"Failed to create real session: {err}")
        sys.exit(1)

    session_manager.reclaim_session(tab_id, None, "testuser")

    # Start the reader so it populates the buffer and last_seen
    from src.gateways.terminal_socket import session_output_reader
    from src.app import socketio

    socketio.start_background_task(session_output_reader, tab_id)

    # Wait for the bash prompt to appear and become idle
    logger.info("Waiting for session to become idle...")
    time.sleep(2)

    # Make sure we have a prompt in the buffer
    os.write(session_obj.fd, b"PS1='test_prompt$ '\n")
    time.sleep(1)
    os.write(session_obj.fd, b"echo ready\n")
    time.sleep(2)

    # 2. Add a schedule
    sched_id = schedule_manager.add_schedule(
        name="Integration Test Schedule",
        target_host_id="local",
        task_prompt="echo 'Hello Integration Test'",
        cron_expr="once",
        wait_for_idle=True,
    )
    logger.info(f"Added schedule {sched_id}")

    # 2. Trigger the scheduler manually
    logger.info("Triggering scheduler...")
    automation_scheduler.process_due_tasks()

    # 3. Wait for execution
    logger.info("Waiting for execution to complete...")
    for _ in range(10):
        jobs = schedule_manager.list_jobs()
        if jobs and jobs[0]["status"] == "completed":
            break
        time.sleep(1)

    jobs = schedule_manager.list_jobs()
    if not jobs:
        logger.error("No jobs found!")
        sys.exit(1)

    job = jobs[0]
    logger.info(f"Job Status: {job['status']}")
    logger.info(f"Job Exit Code: {job['exit_code']}")
    logger.info(f"Job Output: {job['output']}")

    if (
        job["exit_code"] == 0
        and "Hello Integration Test" in job["output"]
        and "___GAB_START___" not in job["output"]
    ):
        logger.info("Integration Test PASSED!")
    else:
        logger.error("Integration Test FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    # Need to run in an eventlet context if we are using background tasks
    # But for a simple test we can just run it
    # Note: TerminalService uses eventlet
    run_integration_test()
