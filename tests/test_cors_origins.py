import pytest
from unittest.mock import patch
import sys
import importlib
from src.config import env_config


def test_cors_origins_enforcement_from_env(monkeypatch):
    """
    Test that when auth bypass is disabled, ALLOWED_ORIGINS sets the cors origins.
    """
    monkeypatch.setenv("BYPASS_AUTH_FOR_TESTING", "")
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://gemini.hackedyour.info,https://gemini-dev.hackedyour.info",
    )

    # Reload config first
    importlib.reload(sys.modules["src.config"])
    from src.config import env_config

    assert (
        env_config.ALLOWED_ORIGINS_RAW
        == "https://gemini.hackedyour.info,https://gemini-dev.hackedyour.info"
    )

    with patch("flask_socketio.SocketIO") as mock_sio:
        if "src.app" in sys.modules:
            del sys.modules["src.app"]
        import src.app

        # We find the mock call args
        call_args = mock_sio.call_args
        assert call_args is not None
        assert call_args.kwargs.get("cors_allowed_origins") == [
            "https://gemini.hackedyour.info",
            "https://gemini-dev.hackedyour.info",
        ]


def test_cors_origins_fallback_when_empty(monkeypatch):
    """
    Test that when auth bypass is disabled and ALLOWED_ORIGINS is empty,
    it falls back to '*' and prints a warning.
    """
    monkeypatch.setenv("BYPASS_AUTH_FOR_TESTING", "")
    monkeypatch.setenv("ALLOWED_ORIGINS", "")

    # Reload config first
    importlib.reload(sys.modules["src.config"])
    from src.config import env_config

    with patch("flask_socketio.SocketIO") as mock_sio:
        if "src.app" in sys.modules:
            del sys.modules["src.app"]
        import src.app

        call_args = mock_sio.call_args
        assert call_args is not None
        assert call_args.kwargs.get("cors_allowed_origins") == "*"
