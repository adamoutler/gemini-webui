import pytest
from src.services.schedule_manager import ScheduleManager


@pytest.fixture
def temp_schedule_manager(tmp_path):
    # Pass tmp_path as data_dir to keep tests isolated
    manager = ScheduleManager(data_dir=str(tmp_path))
    return manager


def test_init_db(temp_schedule_manager):
    # db_path should be created in the tmp_path / "automation"
    assert "automation.db" in str(temp_schedule_manager.db_path)

    # Check if tables exist
    with temp_schedule_manager._get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row["name"] for row in cursor.fetchall()]
        assert "schedules" in tables
        assert "automation_jobs" in tables


def test_crud_schedules(temp_schedule_manager):
    # Add a schedule
    sched_id = temp_schedule_manager.add_schedule(
        name="Test Schedule",
        target_host_id="local",
        task_prompt="echo hello",
        cron_expr="once",
        wait_for_idle=True,
    )

    assert sched_id is not None

    # Get the schedule
    sched = temp_schedule_manager.get_schedule(sched_id)
    assert sched is not None
    assert sched["name"] == "Test Schedule"
    assert sched["target_host_id"] == "local"
    assert sched["task_prompt"] == "echo hello"
    assert sched["cron_expr"] == "once"
    assert sched["wait_for_idle"] == 1

    # List schedules
    schedules = temp_schedule_manager.list_schedules()
    assert len(schedules) == 1
    assert schedules[0]["id"] == sched_id

    # Update run times
    temp_schedule_manager.update_schedule_run_times(sched_id, 1000.0, 2000.0)
    sched = temp_schedule_manager.get_schedule(sched_id)
    assert sched["last_run_at"] == 1000.0
    assert sched["next_run_at"] == 2000.0

    # Delete schedule
    deleted = temp_schedule_manager.delete_schedule(sched_id)
    assert deleted is True

    # Verify deletion
    sched = temp_schedule_manager.get_schedule(sched_id)
    assert sched is None
    schedules = temp_schedule_manager.list_schedules()
    assert len(schedules) == 0


def test_crud_automation_jobs(temp_schedule_manager):
    # Add a job
    job_id = temp_schedule_manager.add_job(
        schedule_id="dummy_sched_id",
        status="completed",
        output="task output",
        exit_code=0,
    )
    assert job_id is not None

    # List jobs
    jobs = temp_schedule_manager.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["schedule_id"] == "dummy_sched_id"
    assert jobs[0]["status"] == "completed"
    assert jobs[0]["output"] == "task output"
    assert jobs[0]["exit_code"] == 0

    # List jobs by schedule
    jobs = temp_schedule_manager.list_jobs(schedule_id="dummy_sched_id")
    assert len(jobs) == 1

    # List jobs by wrong schedule
    jobs = temp_schedule_manager.list_jobs(schedule_id="wrong_id")
    assert len(jobs) == 0
