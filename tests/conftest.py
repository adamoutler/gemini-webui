import os

os.environ["SKIP_MONKEY_PATCH"] = "true"

import time
import subprocess
import pytest
import signal


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    return data_dir


@pytest.fixture(scope="session")
def server(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    import random

    port = str(random.randint(10000, 20000))
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(test_data_dir)
    env["GEMINI_BIN"] = "gemini"
    env["GEMWEBUI_HARNESS"] = "1"
    env["FLASK_USE_RELOADER"] = "false"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"  # Server SHOULD monkeypatch
    env["SKIP_MULTIPLEXER"] = "true"

    mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock")
    env["PATH"] = f"{mock_dir}:{env.get('PATH', '')}"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    process = subprocess.Popen(
        [python_bin, "-m", "src.app"],
        env=env,
        cwd=project_root,
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
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
            pytest.fail("Server failed to start")
    else:
        pytest.fail("Server health check timed out")

    yield f"http://127.0.0.1:{port}"

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except OSError:
        pass
    process.wait()


@pytest.fixture
def app_obj(test_data_dir):
    from src.app import app as flask_app

    flask_app.config["DATA_DIR"] = str(test_data_dir)
    return flask_app


@pytest.fixture
def client(test_data_dir):
    from src.app import app, init_app

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
