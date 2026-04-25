import os

os.environ["SKIP_MONKEY_PATCH"] = "true"
os.environ["SKIP_MULTIPLEXER"] = "true"

import time
import subprocess
import pytest
import signal
import requests


@pytest.fixture(autouse=True)
def clear_server_sessions(request, test_data_dir):
    # Check for any of the common server fixtures
    server_fixtures = [
        "server",
        "custom_server",
        "csrf_enabled_server",
        "csrf_enabled_server_csrf",
        "authenticated_server",
        "docker_server",
        "ssh_test_server",
    ]

    for fixture_name in server_fixtures:
        if fixture_name in request.fixturenames:
            try:
                server_val = request.getfixturevalue(fixture_name)
                server_url = getattr(server_val, "url", server_val)
                requests.get(f"{server_url}/api/sessions/terminate_all", timeout=5)

                if "test_data_dir" in request.fixturenames:
                    data_dir = request.getfixturevalue("test_data_dir")
                    for fname in [
                        "gemini_mock_sessions.json",
                        "gemini_mock_state.json",
                        "persisted_sessions.json",
                    ]:
                        path = os.path.join(str(data_dir), fname)
                        if os.path.exists(path):
                            os.remove(path)
                    import glob

                    for f in glob.glob(os.path.join(str(data_dir), "*.uuid")):
                        os.remove(f)
                break
            except Exception:
                pass

    # Also explicitly clear persisted sessions to avoid bleed
    persisted_file = test_data_dir / "persisted_sessions.json"
    if persisted_file.exists():
        try:
            persisted_file.unlink()
        except OSError:
            pass


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    return data_dir


@pytest.fixture(scope="module")
def server(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = str(s.getsockname()[1])
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(test_data_dir)
    env["GEMINI_BIN"] = "gemini"
    env["GEMWEBUI_HARNESS"] = "1"
    env["FLASK_USE_RELOADER"] = "false"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"  # Server SHOULD monkeypatch
    env["SKIP_MULTIPLEXER"] = "true"
    env["PYTHONUNBUFFERED"] = "1"

    mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock")
    env["PATH"] = f"{mock_dir}:{env.get('PATH', '')}"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    process = subprocess.Popen(
        [python_bin, "-m", "src.app"],
        env=env,
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for server to be ready
    import requests

    max_retries = 20
    for i in range(max_retries):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if resp.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
        if process.poll() is not None:
            pytest.fail(f"Server failed to start. (stdout discarded)")
    else:
        pytest.fail(f"Server health check timed out. (stdout discarded)")

    yield f"http://127.0.0.1:{port}"

    try:
        try:
            if os.getpgid(process.pid) != os.getpgrp():
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                os.kill(process.pid, signal.SIGKILL)
        except OSError:
            pass
    except Exception:
        pass
    try:
        process.wait(timeout=5)
    except Exception:
        pass


@pytest.fixture
def app_obj(test_data_dir):
    from src.app import app as flask_app

    flask_app.config["DATA_DIR"] = str(test_data_dir)
    return flask_app


@pytest.fixture
def client(test_data_dir, monkeypatch):
    from src.app import app, init_app

    monkeypatch.setenv("DATA_DIR", str(test_data_dir))
    app.config["TESTING"] = True
    app.config["BYPASS_AUTH_FOR_TESTING"] = "true"
    app.config["WTF_CSRF_ENABLED"] = False
    os.environ["BYPASS_AUTH_FOR_TESTING"] = "true"
    os.environ["WTF_CSRF_ENABLED"] = "false"
    os.environ["DATA_DIR"] = str(test_data_dir)
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["DATA_DIR"] = str(test_data_dir)

    init_app()

    with app.test_client() as client:
        with app.app_context():
            with client.session_transaction() as sess:
                sess["authenticated"] = True
                sess["user_id"] = "admin"
        yield client


import unittest.mock


@pytest.fixture(autouse=True)
def safe_killpg_fixture(request):
    if "e2e" in request.node.nodeid:
        yield
        return
    """
    Prevents tests from accidentally killing real processes on the host.
    Any call to os.killpg will be ignored unless explicitly tested.
    """
    with unittest.mock.patch("os.killpg") as mock_killpg, unittest.mock.patch(
        "os.kill"
    ) as mock_kill, unittest.mock.patch(
        "os.getpgid", return_value=123456789
    ) as mock_getpgid:
        yield
