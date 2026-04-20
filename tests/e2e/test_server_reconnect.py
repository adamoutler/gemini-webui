import pytest
import time
import subprocess
import os
import signal
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def custom_server(tmp_path, playwright):
    persisted_file = tmp_path / "persisted_sessions.json"
    if persisted_file.exists():
        try:
            persisted_file.unlink()
        except OSError:
            pass

    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = str(s.getsockname()[1])
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(tmp_path)
    env["FLASK_USE_RELOADER"] = "false"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    def start_server():
        proc = subprocess.Popen(
            [python_bin, "-m", "src.app"],
            env=env,
            cwd=project_root,
            start_new_session=True,
        )
        import requests

        ready = False
        for _ in range(90):
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
                if resp.status_code == 200:
                    ready = True
                    break
            except requests.RequestException:
                pass
            time.sleep(1)

        if not ready:
            raise Exception(f"Failed to start server on port {port} in time")
        return proc

    process = start_server()
    url = f"http://127.0.0.1:{port}"

    class ServerController:
        def __init__(self, process, start_fn, url):
            self.process = process
            self.start_fn = start_fn
            self.url = url

        def stop(self):
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()
            except OSError:
                pass

            # Clear persisted sessions so the new server does not try to restore
            # dead PTY file descriptors which immediately emit session-terminated.
            persisted_file = tmp_path / "persisted_sessions.json"
            if persisted_file.exists():
                try:
                    persisted_file.unlink()
                except OSError:
                    pass

        def start(self):
            self.process = self.start_fn()

    controller = ServerController(process, start_server, url)
    yield controller
    controller.stop()


@pytest.mark.timeout(40)
def test_auto_reconnect_after_server_restart(custom_server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # 1. Load page and connect
    page.goto(custom_server.url)
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=5000)

    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()

    # Wait for terminal to load and status to be connected
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=5000)
    status_el = page.locator("#connection-status")
    expect(status_el).to_have_text("local")

    # 2. Stop server
    custom_server.stop()

    # 3. Verify UI shows "Reconnecting..."
    expect(status_el).to_have_text("Reconnecting...", timeout=10000)

    # 4. Wait a bit then restart server
    time.sleep(2)
    custom_server.start()

    # 5. Verify UI auto-reconnects and shows "local" again (without manual refresh)
    try:
        expect(status_el).to_have_text("local", timeout=15000)
    except Exception as e:
        # If it fails, capture the DOM to understand why it reverted to launcher
        body_html = page.evaluate("document.body.innerHTML")
        print(f"FAILED DOM DUMP:\n{body_html}\n\nException: {e}")
        raise
    context.close()
    browser.close()
