import eventlet
import time
import logging
from src.services.schedule_manager import schedule_manager
from src.services.automation_bridge import automation_bridge

logger = logging.getLogger(__name__)


class AutomationScheduler:
    def __init__(self):
        self.running = False
        self._thread = None

    def start(self):
        if not self.running:
            self.running = True
            from src.app import socketio

            self._thread = socketio.start_background_task(self.run_loop)
            logger.info("Automation scheduler started.")

    def run_loop(self):
        while self.running:
            try:
                self.process_due_tasks()
                self.reap_stale_jobs()
            except Exception as e:
                logger.error(f"Error in automation scheduler loop: {e}")
            eventlet.sleep(30)  # Check every 30 seconds

    def reap_stale_jobs(self):
        now = time.time()
        # Any job running for more than 5 minutes is considered stale and failed
        stale_threshold = now - 300
        with schedule_manager._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE automation_jobs SET status = 'failed', output = output || '\n[Error: Reaped after timeout]', exit_code = -1 WHERE status = 'running' AND timestamp < ?",
                (stale_threshold,),
            )
            if cursor.rowcount > 0:
                logger.warning(f"Reaped {cursor.rowcount} stale automation jobs.")
            conn.commit()

    def process_due_tasks(self):
        schedules = schedule_manager.list_schedules()
        now = time.time()
        for sched in schedules:
            if not sched.get("is_active"):
                continue

            next_run_at = sched.get("next_run_at")
            if next_run_at and now >= next_run_at:
                target_host_id = sched["target_host_id"]
                wait_for_idle = bool(sched.get("wait_for_idle", True))

                if wait_for_idle and not automation_bridge.is_host_idle(target_host_id):
                    logger.info(
                        f"Schedule {sched['id']} is due, but host {target_host_id} is busy. Waiting for idle."
                    )
                    continue

                logger.info(f"Executing schedule {sched['id']} on {target_host_id}")
                automation_bridge.execute_task(
                    target_host_id,
                    sched["task_prompt"],
                    sched["prompt_context"],
                    schedule_id=sched["id"],
                )

                cron_expr = sched.get("cron_expr", "once")
                if cron_expr == "once":
                    with schedule_manager._get_connection() as conn:
                        conn.execute(
                            "UPDATE schedules SET is_active = 0, last_run_at = ?, updated_at = ? WHERE id = ?",
                            (now, now, sched["id"]),
                        )
                        conn.commit()
                else:
                    parts = cron_expr.split()
                    if len(parts) == 2:
                        try:
                            freq = int(parts[0])
                            unit = parts[1]
                            interval = 60
                            if unit == "minutes":
                                interval = freq * 60
                            elif unit == "hours":
                                interval = freq * 3600
                            elif unit == "days":
                                interval = freq * 86400
                            elif unit == "weeks":
                                interval = freq * 604800
                            elif unit == "months":
                                interval = freq * 2592000

                            next_run = now + interval
                            schedule_manager.update_schedule_run_times(
                                sched["id"], now, next_run
                            )
                        except ValueError:
                            logger.error(
                                f"Invalid cron_expr '{cron_expr}' for schedule {sched['id']}"
                            )
                            # Deactivate on parse fail to prevent infinite loop spam
                            with schedule_manager._get_connection() as conn:
                                conn.execute(
                                    "UPDATE schedules SET is_active = 0 WHERE id = ?",
                                    (sched["id"],),
                                )
                                conn.commit()
                    else:
                        schedule_manager.update_schedule_run_times(
                            sched["id"], now, now + 3600
                        )


automation_scheduler = AutomationScheduler()
