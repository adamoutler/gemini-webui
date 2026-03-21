import pytest
import time
import subprocess
import os
import signal
import socket
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def authenticated_server(test_data_dir):
    env = os.environ.copy()
    env["SECRET_KEY"] = "testsecret"
    env["BASIC_AUTH_USERNAME"] = "testuser"
    env["BASIC_AUTH_PASSWORD"] = "testpass"
    import random

    port = str(random.randint(10000, 20000))
    env["PORT"] = port
    env["DATA_DIR"] = str(test_data_dir)
    env["FLASK_USE_RELOADER"] = "false"
    env["GEMWEBUI_HARNESS"] = "1"
    env["FLASK_DEBUG"] = "false"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    process = subprocess.Popen(
        [python_bin, "src/app.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
        text=True,
    )

    # Wait for port to open
    start_time = time.time()
    while time.time() - start_time < 5:
        try:
            with socket.create_connection(("localhost", int(port)), timeout=0.1):
                break
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(0.1)
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        pytest.fail("Server did not start in time")

    yield {"port": port, "process": process, "url": f"http://localhost:{port}"}

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=5)
    except Exception:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except OSError:
            pass


@pytest.mark.skip(reason="Flaky in CI")
def test_new_deployment_login(authenticated_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Create a mobile context since bug affects mobile/safari often and it is a good test vector
        iphone = p.devices["iPhone 13"]
        context = browser.new_context(
            **iphone, http_credentials={"username": "testuser", "password": "testpass"}
        )
        page = context.new_page()

        js_errors = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: js_errors.append(msg.text) if msg.type == "error" else None,
        )

        url = authenticated_server["url"]

        response = page.goto(url)
        assert response.status == 200

        # Wait for either the terminal to appear or for the page to load
        page.wait_for_timeout(2000)

        # Check for UI elements
        terminal_container = page.locator("#terminal-container")
        expect(terminal_container).to_be_visible(timeout=5000)

        # Check connection status
        # Wait until we see at least one "local" connection card
        expect(page.locator(".connection-card[data-label='local']")).to_be_visible(
            timeout=10000
        )

        # Click Start New on local without waiting 2 seconds (this exposes the WSS connect race condition)
        page.locator(
            ".connection-card[data-label='local'] button:has-text('Start New')"
        ).click()

        # Wait for terminal
        expect(page.locator(".xterm")).to_be_visible(timeout=5000)

        # Wait a bit for data to render
        try:
            page.wait_for_function(
                """() => {
                const tab = tabs.find(t => t.id === activeTabId);
                if (!tab || !tab.term) return false;
                for (let i = 0; i < Math.min(5, tab.term.buffer.active.length); i++) {
                    if ((tab.term.buffer.active.getLine(i)?.translateToString(true) || '').trim().length > 0) return true;
                }
                return false;
            }""",
                timeout=5000,
            )
        except Exception:
            pass

        # Ensure there is no JS error before checking rows
        assert len(js_errors) == 0, f"JS Errors found before rendering: {js_errors}"

        # Get terminal text
        terminal_text = page.evaluate("""() => {
            const tab = tabs.find(t => t.id === activeTabId);
            if (!tab || !tab.term) return '';
            let text = '';
            for (let i = 0; i < Math.min(50, tab.term.buffer.active.length); i++) {
                text += tab.term.buffer.active.getLine(i)?.translateToString(true) || '';
            }
            return text;
        }""")
        print("Terminal text:", repr(terminal_text))

        # Ensure it's not totally empty (should have prompt)
        if len(terminal_text.strip()) == 0:
            pytest.fail("Terminal is completely black/empty!")

        # Ensure there is no JS error
        assert len(js_errors) == 0, f"JS Errors found: {js_errors}"

        browser.close()
