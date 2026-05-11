from dataclasses import dataclass
from typing import Optional


@dataclass
class Schedule:
    id: str
    name: str
    target_host_id: str
    prompt_context: str
    task_prompt: str
    cron_expr: str
    wait_for_idle: bool
    last_run_at: Optional[float]
    next_run_at: Optional[float]
    is_active: bool


@dataclass
class AutomationJob:
    id: str
    schedule_id: Optional[str]
    status: str
    output: str
    exit_code: Optional[int]
    timestamp: float
