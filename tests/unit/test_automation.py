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


def test_execution_engine_and_reaper(temp_schedule_manager, monkeypatch):
    import time
    from unittest.mock import MagicMock
    from src.services.automation_bridge import automation_output_reader
    from src.services.automation_scheduler import automation_scheduler

    # Override the singleton schedule_manager with our temp one for the test
    monkeypatch.setattr(
        "src.services.automation_bridge.schedule_manager", temp_schedule_manager
    )
    monkeypatch.setattr(
        "src.services.automation_scheduler.schedule_manager", temp_schedule_manager
    )

    # Add a job that is old and running to test reaper
    old_job_id = temp_schedule_manager.add_job("sched_1", "running")
    now = time.time()
    # Mock its timestamp to be very old
    with temp_schedule_manager._get_connection() as conn:
        conn.execute(
            "UPDATE automation_jobs SET timestamp = ? WHERE id = ?",
            (now - 1000, old_job_id),
        )
        conn.commit()

    # Run reaper
    automation_scheduler.reap_stale_jobs()

    # Verify the old job is reaped
    jobs = temp_schedule_manager.list_jobs()
    for j in jobs:
        if j["id"] == old_job_id:
            assert j["status"] == "failed"
            assert j["exit_code"] == -1
            assert "[Error: Reaped after timeout]" in j["output"]

    # Test the automation_output_reader
    class DummySession:
        def __init__(self):
            self.active = True
            self.pid = 99999
            self.buffer = []

    dummy_session = DummySession()
    monkeypatch.setattr(
        "src.services.automation_bridge.session_manager.get_session",
        lambda tid: dummy_session,
    )
    monkeypatch.setattr(
        "src.services.automation_bridge.session_manager.remove_session",
        lambda tid: None,
    )
    monkeypatch.setattr(
        "src.services.automation_bridge.kill_and_reap", lambda pid: None
    )

    # We also need to mock socketio.emit and sleep to prevent errors
    mock_socketio = MagicMock()

    new_job_id = temp_schedule_manager.add_job("sched_2", "queued")

    # Provide a side effect for sleep that simulates buffer filling over time
    def mock_sleep(seconds):
        start_marker = f"___GAB_START_{new_job_id}___"
        end_marker = f"___GAB_END_{new_job_id}___"
        if len(dummy_session.buffer) == 0:
            dummy_session.buffer.append(
                f"echo {start_marker}; echo 'some output here'; echo {end_marker} $?\\n"
            )
            dummy_session.buffer.append(f"{start_marker}\\n")
            dummy_session.buffer.append("some output here\\n")
        elif len(dummy_session.buffer) == 3:
            dummy_session.buffer.append(f"{end_marker} 42\\n")
            dummy_session.buffer.append("local$ ")
        else:
            dummy_session.active = False

    mock_socketio.sleep.side_effect = mock_sleep
    monkeypatch.setattr("src.services.automation_bridge.eventlet.sleep", mock_sleep)
    monkeypatch.setattr("src.app.socketio", mock_socketio)

    automation_output_reader("dummy_tab", new_job_id, 0)

    # Verify the job was updated correctly
    with temp_schedule_manager._get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM automation_jobs WHERE id = ?", (new_job_id,)
        )
        job = dict(cursor.fetchone())

    assert job["status"] == "completed"
    assert job["exit_code"] == 42
    assert "some output here" in job["output"]
    assert "echo" not in job["output"]
