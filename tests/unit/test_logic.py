import os
from src.config import get_config_paths
from src.app import validate_ssh_target, set_winsize


def test_validate_ssh_target():
    assert validate_ssh_target("user@host") is True
    assert validate_ssh_target("host.example.com") is True
    assert validate_ssh_target("user@192.168.1.1") is True
    assert validate_ssh_target("user@host:2222") is True
    assert validate_ssh_target("invalid-target!") is False
    assert validate_ssh_target("user@host; rm -rf /") is False


from unittest.mock import patch


def test_get_config_paths_failover(tmp_path):
    with patch("src.config.env_config") as mock_env:
        # Simulate that the initially configured DATA_DIR is not writable
        mock_env.DATA_DIR = "/ro/data_dir"

        orig_access = (
            os.access
        )  # Mock os.access to return False for the RO dir and True for /tmp

        def mock_access(path, mode):
            if path in ("/ro/data_dir", "/ro"):
                return False
            if path == "/tmp":
                return True
            return orig_access(path, mode)

        with patch("os.access", side_effect=mock_access):
            with patch("os.makedirs") as mock_makedirs:
                with patch("os.path.exists", return_value=True):
                    d, c, s = get_config_paths()

                    # Verify it fell back to /tmp/gemini-data
                    assert d == "/tmp/gemini-data"
                    assert c == "/tmp/gemini-data/config.json"
                    assert s == "/tmp/gemini-data/.ssh"
                    mock_makedirs.assert_called_once_with(
                        "/tmp/gemini-data", exist_ok=True
                    )


def test_set_winsize_no_error():
    with patch("src.app.struct.pack") as mock_pack:
        mock_pack.return_value = b"mocked_winsize"
        with patch("src.app.fcntl.ioctl") as mock_ioctl:
            with patch("src.app.termios.TIOCSWINSZ", 21524, create=True):
                set_winsize(42, 24, 80, 0, 0)
                mock_pack.assert_called_once_with("HHHH", 24, 80, 0, 0)
                mock_ioctl.assert_called_once_with(42, 21524, b"mocked_winsize")
