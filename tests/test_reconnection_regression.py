import pytest
import time
import os
import signal
import subprocess
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def custom_server(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    import random

    port = str(random.randint(10000, 20000))
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(test_data_dir)
    env["FLASK_USE_RELOADER"] = "false"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    def start_server():
        proc = subprocess.Popen(
            [python_bin, "-m", "src.app"],
            env=env,
            cwd=project_root,
            preexec_fn=os.setsid,
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


class TestReconnectionRegression:
    @pytest.mark.timeout(60)
    def test_reconnection_regression(self, custom_server):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()

            # Capture console messages
            console_logs = []

            def log_console(msg):
                console_logs.append(msg.text)
                print(f"CONSOLE: {msg.text}")

            page = context.new_page()
            page.on("console", log_console)

            # 1. Start the server (using custom_server)
            # 2. Visit the select a connection page (the root URL)
            page.goto(custom_server.url)

            # Wait for service worker to install
            page.wait_for_timeout(2000)

            expect(page.get_by_text("Select a Connection").first).to_be_visible(
                timeout=5000
            )

            # 3. Observe green indicator on Local connection
            local_health = page.locator(
                'div[data-label="local"] .connection-title span[id$="_health_local"]'
            )

            try:
                expect(local_health).to_have_text("🟢", timeout=15000)
            except AssertionError:
                # If CI is slow and Socket.IO didn't bind in time for the first load, reload the page
                page.reload()
                expect(local_health).to_have_text("🟢", timeout=15000)

            # 4. Restart the server (stop then start)
            # To simulate the server being down long enough for the UI to notice
            custom_server.stop()

            # 5. Observe red indicator
            # UI checks every 10 seconds, so it may take up to 20-25 seconds to turn red
            expect(local_health).to_have_text("🔴", timeout=30000)

            # Wait a bit to ensure the SW caches the failed responses if it does
            page.wait_for_timeout(5000)

            import os

            os.makedirs("docs/qa-images/GEMWEBUI-265", exist_ok=True)
            page.screenshot(path="docs/qa-images/GEMWEBUI-265/disconnected.png")

            # 6. Observe accurate and helpful error messages in the browser console logs describing the condition.
            error_found = any(
                "error" in log.lower()
                or "fail" in log.lower()
                or "disconnect" in log.lower()
                or "refused" in log.lower()
                for log in console_logs
            )
            assert error_found, "Expected error or disconnect messages in console logs"

            # Now restart the server
            custom_server.start()

            # Give the server a moment to be fully ready
            page.wait_for_timeout(2000)

            # 7. Refresh browser (standard F5/page.reload(), no cache wipe)
            page.reload()

            expect(page.get_by_text("Select a Connection").first).to_be_visible(
                timeout=5000
            )

            # 8. Observe indicators turn green
            local_health2 = page.locator(
                'div[data-label="local"] .connection-title span[id$="_health_local"]'
            )
            expect(local_health2).to_have_text("🟢", timeout=15000)

            page.screenshot(path="docs/qa-images/GEMWEBUI-265/reconnected.png")

            context.close()
            browser.close()
