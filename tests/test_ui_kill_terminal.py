import pytest
import os
import subprocess
import time
import signal
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def test_server(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    env["WTF_CSRF_ENABLED"] = "false"
    env["FLASK_USE_RELOADER"] = "false"
    import random

    port = str(random.randint(10000, 20000))
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(test_data_dir)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    proc = subprocess.Popen(
        [python_bin, "-m", "src.app"], env=env, cwd=project_root, preexec_fn=os.setsid
    )
    import requests

    for _ in range(20):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if resp.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)

    url = f"http://127.0.0.1:{port}"
    yield url

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
    except OSError:
        pass


@pytest.mark.timeout(30)
def test_kill_terminal_button(test_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(test_server)

        # Click Start New Local Terminal
        btns = page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=5000)
        btns.first.click()

        # Wait for terminal
        expect(page.locator("#active-connection-info")).to_be_visible(timeout=5000)

        # Wait a moment for connection
        page.wait_for_timeout(2000)

        # Set up a dialog handler to automatically accept the confirm() prompt
        page.once("dialog", lambda dialog: dialog.accept())

        # Click Kill
        page.click('button:has-text("Kill")')

        # Wait and verify that we are back at the launcher or the tab is closed
        # When closed, active connection info should be hidden or the tab is gone
        expect(
            page.locator('.tab-instance.active:has-text("Local Connection")')
        ).to_be_hidden(timeout=5000)

        context.close()
        browser.close()
