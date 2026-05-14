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

    # 1. Add a dummy session to prove idle logic
    import pty

    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("bash", ["bash", "--noprofile", "--norc"], os.environ)

    class MockSession:
        def __init__(self):
            self.tab_id = "dummy_tab"
            self.ssh_target = "local"
            self.ssh_dir = "~"
            self.title = "Test Session"
            self.last_seen = time.time() - 10
            self.buffer = ["user@host:~$ "]
            self.active = True
            self.fd = fd
            self.pid = pid
            self.user_id = "automation"
            import codecs

            self.decoder = codecs.getincrementaldecoder("utf-8")()

        def append_buffer(self, data):
            self.buffer.append(data)

    dummy_session = MockSession()
    session_manager.sessions["dummy_tab"] = dummy_session

    # Start the reader
    from src.gateways.terminal_socket import session_output_reader
    from src.app import socketio

    socketio.start_background_task(session_output_reader, "dummy_tab")

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
