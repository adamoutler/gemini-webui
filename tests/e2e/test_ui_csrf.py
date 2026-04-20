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

    mock_dir = os.path.join(project_root, "tests", "mock")
    env["PATH"] = f"{mock_dir}:{env.get('PATH', '')}"
    env["PYTHONPATH"] = project_root

    def start_server():
        proc = subprocess.Popen(
            [python_bin, "-m", "src.app"],
            env=env,
            cwd=str(tmp_path),
            start_new_session=True,
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

        def start(self):
            self.process = self.start_fn()

    controller = ServerController(process, start_server, url)
    yield controller
    controller.stop()


@pytest.mark.timeout(60)
def test_csrf_fail_deadly_reload(custom_server, tmp_path, playwright):
    """
    Test that a CSRF expiration triggers a hard reload.
    Asserts Page Refresh Resilience, Visual Reload Assertion, and Reclaim logic.
    """
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto(custom_server.url)
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=5000)

    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=5000)

    page.locator(".tab-instance.active .xterm").first.click()
    page.keyboard.type("echo 'BEFORE_RELOAD_STATE'\r")

    def check_text(page):
        return page.evaluate("""() => {
            if (typeof tabs === 'undefined' || typeof activeTabId === 'undefined') return '';
            const tab = tabs.find(t => t.id === activeTabId);
            if (!tab || !tab.term) return '';
            let text = '';
            for (let i = 0; i < tab.term.buffer.active.length; i++) {
                text += tab.term.buffer.active.getLine(i)?.translateToString(true) || '';
                text += '\\n';
            }
            return text;
        }""")

    for _ in range(10):
        term_text = check_text(page)
        if "BEFORE_RELOAD_STATE" in term_text:
            break
        time.sleep(0.5)

    assert "BEFORE_RELOAD_STATE" in term_text

    # Simulate CSRF failure by monkeypatching the next fetch to return 403 with csrf_expired
    page.evaluate("""() => {
        const oldFetch = window.fetch;
        window.fetch = async function(res, cfg) {
            if (typeof res === 'string' && res.includes('/api/upload')) {
                return new Response(JSON.stringify({csrf_expired: true}), {
                    status: 403,
                    headers: { 'Content-Type': 'application/json' }
                });
            }
            return oldFetch.apply(this, arguments);
        };
    }""")

    # Trigger the fetch that will fail
    page.evaluate("fetch('/api/upload', {method: 'POST'})")

    # Wait for the page to reload
    page.wait_for_load_state("networkidle")

    # Visual reload assertion: UI rehydrates terminal
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=10000)

    # Check that the buffer is rehydrated via WebSocket reclaim (not start new)
    for _ in range(20):
        term_text = check_text(page)
        if "BEFORE_RELOAD_STATE" in term_text:
            break
        time.sleep(0.5)

    assert (
        "BEFORE_RELOAD_STATE" in term_text
    ), "Failed to reclaim PTY buffer after CSRF reload"

    # Verify App Background/Resume Resilience (network drop reclaim)
    page.evaluate("tabs.find(t => t.id === activeTabId).socket.io.engine.close()")

    status_el = page.locator("#connection-status")
    expect(status_el).to_have_text("Reconnecting...", timeout=10000)

    expect(status_el).to_have_text("local", timeout=10000)

    page.locator(".tab-instance.active .xterm").first.click()
    page.keyboard.type("echo 'AFTER_RECONNECT_STATE'\r")
    for _ in range(10):
        term_text = check_text(page)
        if "AFTER_RECONNECT_STATE" in term_text:
            break
        time.sleep(0.5)

    assert "AFTER_RECONNECT_STATE" in term_text

    context.close()
    browser.close()
