import os
os.environ['SKIP_MONKEY_PATCH'] = 'true'

import time
import random
import subprocess
import pytest
import json
import shutil
import signal
from src.app import app, init_app

@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    return data_dir

@pytest.fixture(scope="session")
def server(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    env["PORT"] = "5005"
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(test_data_dir)
    env["GEMINI_BIN"] = "gemini"
    env["FLASK_USE_RELOADER"] = "false"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false" # Server SHOULD monkeypatch
    
    mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock")
    env["PATH"] = f"{mock_dir}:{env.get('PATH', '')}"
    
    port = "5005"
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")
    
    process = subprocess.Popen(
        [python_bin, "src/app.py"],
        env=env,
        cwd=project_root,
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    
    # Wait for server to be ready
    import requests
    max_retries = 20
    for i in range(max_retries):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if resp.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
        if process.poll() is not None:
            pytest.fail("Server failed to start")
    else:
        pytest.fail("Server health check timed out")
    
    yield f"http://127.0.0.1:{port}"
    
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:
        pass
    process.wait()

@pytest.fixture
def app_obj(test_data_dir):
    from src.app import app as flask_app
    flask_app.config['DATA_DIR'] = str(test_data_dir)
    return flask_app

@pytest.fixture
def client(test_data_dir):
    import sys
    if 'src.app' in sys.modules:
        import importlib
        importlib.reload(sys.modules['src.app'])
    from src.app import app, init_app
    
    app.config['TESTING'] = True
    app.config['BYPASS_AUTH_FOR_TESTING'] = 'true'
    app.config['DATA_DIR'] = str(test_data_dir)
    
    init_app()
    
    with app.test_client() as client:
        with app.app_context():
            with client.session_transaction() as sess:
                sess['authenticated'] = True
        yield client
