from unittest.mock import patch, MagicMock
from src.session_manager import Session, SessionManager


def test_session_init_file_cache():
    session = Session("tab1", None, 1234, "user1")
    assert hasattr(session, "file_cache")
    assert session.file_cache == []


def test_session_to_dict_file_cache():
    session = Session("tab1", None, 1234, "user1")
    session.file_cache = ["file1.txt", "dir1/"]
    d = session.to_dict()
    assert "file_cache" in d
    assert d["file_cache"] == ["file1.txt", "dir1/"]


@patch("src.session_manager.subprocess.run")
def test_update_file_cache_local(mock_run):
    manager = SessionManager()
    session = Session("tab1", None, 1234, "user1")
    manager.add_session(session)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "file1.txt\ndir1/\nfile2.py"
    mock_run.return_value = mock_result

    app_config = {"DATA_DIR": "/tmp"}
    manager.update_file_cache("tab1", app_config)

    assert session.file_cache == ["file1.txt", "dir1/", "file2.py"]
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "/bin/sh"
    assert "find ." in args[2]


@patch("src.session_manager.subprocess.run")
def test_update_file_cache_ssh(mock_run):
    manager = SessionManager()
    session = Session(
        "tab2", 1, 1234, "user1", ssh_target="user@host", ssh_dir="~/myproj"
    )
    manager.add_session(session)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "remote_file.txt\nremote_dir/"
    mock_run.return_value = mock_result

    app_config = {"SSH_DIR": "/tmp/.ssh"}
    manager.update_file_cache("tab2", app_config)

    assert session.file_cache == ["remote_file.txt", "remote_dir/"]
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "ssh" in args[0]
    assert "user@host" in args
