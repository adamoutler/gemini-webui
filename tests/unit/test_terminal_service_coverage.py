from src.services.terminal_service import TerminalService


def test_start_session_invalid_target():
    service = TerminalService()
    resp = service.start_session(
        tab_id="tab2",
        user_id="user1",
        ssh_target="invalid target!",
        ssh_dir="",
        resume=False,
        cols=80,
        rows=24,
        env_vars={},
    )
    assert "Invalid SSH target format" in str(resp)


def test_execute_command_invalid():
    service = TerminalService()
    result, status = service.execute_command_sync(
        "non_existent_tab", "ls", prompt="mock_prompt"
    )
    assert status in (400, 404)
