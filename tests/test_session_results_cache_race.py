import threading
import pytest
from src.app import app, register_blueprints

@pytest.fixture(autouse=True)
def init_test_app():
    if not hasattr(app, "blueprints_registered"):
        register_blueprints(app)
        app.blueprints_registered = True

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["BYPASS_AUTH_FOR_TESTING"] = True
    app.config["SECRET_KEY"] = "test_secret"
    with app.test_client() as client:
        yield client


def test_concurrent_list_sessions(client, monkeypatch):
    # Mock fetch_sessions_for_host to simulate work and prevent actual network/fs calls
    monkeypatch.setattr(
        "src.routes.terminal.fetch_sessions_for_host", lambda *args, **kwargs: {"sessions": []}
    )

    # We must patch authenticated_only if it strictly requires session
    # but BYPASS_AUTH_FOR_TESTING usually handles this in the codebase.
    monkeypatch.setenv("BYPASS_AUTH_FOR_TESTING", "true")

    errors = []

    def worker():
        with app.test_client() as client:
            try:
                for _ in range(50):
                    # Hit background fetch
                    resp = client.get("/api/sessions?bg=true")
                    if resp.status_code != 200:
                        errors.append(f"Bad status bg: {resp.status_code}")

                    # Hit cache fetch
                    resp = client.get("/api/sessions?cache=true")
                    if resp.status_code not in (200, 504):
                        errors.append(f"Bad status cache: {resp.status_code}")

                    # Hit foreground fetch
                    resp = client.get("/api/sessions")
                    if resp.status_code not in (200, 504):
                        errors.append(f"Bad status fg: {resp.status_code}")

            except Exception as e:
                errors.append(e)

    threads = []
    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent requests: {errors}"
