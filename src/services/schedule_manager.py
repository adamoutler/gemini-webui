import sqlite3
import uuid
import time
from pathlib import Path
from typing import List, Dict, Optional

from src.config import env_config


class ScheduleManager:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            self.base_dir = Path(env_config.DATA_DIR)
        else:
            self.base_dir = Path(data_dir)

        self.automation_dir = self.base_dir / "automation"
        try:
            self.automation_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = self.automation_dir / "automation.db"
            self._init_db()
        except OSError:
            self.db_path = ":memory:"
            pass

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    target_host_id TEXT NOT NULL,
                    prompt_context TEXT NOT NULL,
                    task_prompt TEXT NOT NULL,
                    cron_expr TEXT NOT NULL,
                    wait_for_idle INTEGER DEFAULT 1,
                    last_run_at REAL,
                    next_run_at REAL,
                    is_active INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS automation_jobs (
                    id TEXT PRIMARY KEY,
                    schedule_id TEXT,
                    status TEXT NOT NULL,
                    output TEXT,
                    exit_code INTEGER,
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()

    def list_schedules(self) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_schedule(self, schedule_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_schedule(
        self,
        name: str,
        target_host_id: str,
        task_prompt: str,
        cron_expr: str,
        wait_for_idle: bool = True,
        prompt_context: str = "",
    ) -> str:
        schedule_id = str(uuid.uuid4())
        now = time.time()

        if not prompt_context:
            prompt_context = "It is currently $(time) and you have been summoned on a timer. Be respectful of the environment. The user has requested you perform the following task: "

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO schedules (
                    id, name, target_host_id, prompt_context, task_prompt, cron_expr, wait_for_idle,
                    last_run_at, next_run_at, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 1, ?, ?)
                """,
                (
                    schedule_id,
                    name,
                    target_host_id,
                    prompt_context,
                    task_prompt,
                    cron_expr,
                    int(wait_for_idle),
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
        return schedule_id

    def update_schedule_run_times(
        self, schedule_id: str, last_run_at: float, next_run_at: float
    ):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE schedules SET last_run_at = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
                (last_run_at, next_run_at, now, schedule_id),
            )
            conn.commit()

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            return cursor.rowcount > 0

    def add_job(
        self,
        schedule_id: Optional[str],
        status: str,
        output: str = "",
        exit_code: Optional[int] = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO automation_jobs (id, schedule_id, status, output, exit_code, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, schedule_id, status, output, exit_code, now),
            )
            conn.commit()
        return job_id

    def list_jobs(self, schedule_id: Optional[str] = None) -> List[Dict]:
        with self._get_connection() as conn:
            if schedule_id:
                cursor = conn.execute(
                    "SELECT * FROM automation_jobs WHERE schedule_id = ? ORDER BY timestamp DESC",
                    (schedule_id,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM automation_jobs ORDER BY timestamp DESC"
                )
            return [dict(row) for row in cursor.fetchall()]


schedule_manager = ScheduleManager()
