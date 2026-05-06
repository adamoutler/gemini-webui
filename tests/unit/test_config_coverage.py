from src.config import EnvConfig


def test_env_config_properties(monkeypatch):
    monkeypatch.setenv("SKIP_MULTIPLEXER", "true")
    monkeypatch.setenv("SKIP_PRELOADER", "true")
    monkeypatch.setenv("FLASK_DEBUG", "false")
    monkeypatch.setenv("FLASK_USE_RELOADER", "false")
    monkeypatch.setenv("ORPHANED_SESSION_TTL", "123")
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("UI_PORT", "8081")
    monkeypatch.setenv("API_PORT", "8082")
    monkeypatch.setenv("SECRET_KEY", "test_secret")

    config = EnvConfig()
    assert config.SKIP_MULTIPLEXER is True
    assert config.SKIP_PRELOADER is True
    assert config.FLASK_DEBUG is False
    assert config.FLASK_USE_RELOADER is False
    assert config.ORPHANED_SESSION_TTL == 123
    assert config.PORT == 8080
    assert config.UI_PORT == 8081
    assert config.API_PORT == 8082
    assert config.SECRET_KEY == "test_secret"


def test_env_config_orphaned_session_ttl_invalid(monkeypatch):
    monkeypatch.setenv("ORPHANED_SESSION_TTL", "invalid")
    config = EnvConfig()
    assert config.ORPHANED_SESSION_TTL is None
