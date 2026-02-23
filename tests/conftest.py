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
    env["DATA_DIR"] = str(test_data_dir)
    env["DEFAULT_SSH_TARGET"] = ""
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    
    time.sleep(5)
    if process.poll() is not None:
        pytest.fail("Server failed to start")
    
    yield f"http://127.0.0.1:{port}"
    
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:
        pass
    process.wait()

@pytest.fixture
def client(test_data_dir):
    app.config['TESTING'] = True
    app.config['BYPASS_AUTH_FOR_TESTING'] = 'true'
    app.config['DATA_DIR'] = str(test_data_dir)
    
    init_app()
    
    with app.test_client() as client:
        with app.app_context():
            with client.session_transaction() as sess:
                sess['authenticated'] = True
        yield client
