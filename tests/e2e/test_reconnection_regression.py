import pytest
import time
import os
import subprocess
import requests
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def docker_server(tmp_path, playwright):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = str(s.getsockname()[1])
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    image_name = "gemwebui-test-image"

    # 1. build and launch a fresh container
    subprocess.run(
        ["docker", "build", "-t", image_name, "."], cwd=project_root, check=True
    )

    container_name = f"gemwebui-test-{port}"

    def start_server():
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "-p",
                f"{port}:5000",
                "-e",
                "BYPASS_AUTH_FOR_TESTING=true",
                "-e",
                "SECRET_KEY=testsecret",
                "-e",
                "ALLOWED_ORIGINS=*",
                "-v",
                f"{tmp_path}:/data",
                image_name,
            ],
            check=True,
        )

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
            raise Exception(
                f"Server in container {container_name} failed to become ready in time"
            )

    start_server()
    url = f"http://127.0.0.1:{port}"

    class ServerController:
        def __init__(self, start_fn, url):
            self.start_fn = start_fn
            self.url = url

        def stop(self):
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

        def start(self):
            self.start_fn()

    controller = ServerController(start_server, url)
    yield controller
    controller.stop()


class TestReconnectionRegression:
    @pytest.mark.timeout(300)
    def test_reconnection_regression(self, docker_server, playwright):
        p = playwright
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # Capture console messages
        console_logs = []

        def log_console(msg):
            console_logs.append(msg.text)
            print(f"CONSOLE: {msg.text}")

        page = context.new_page()
        page.on("console", log_console)

        # 2. Visit the select a connection page (the root URL)
        page.goto(docker_server.url)

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

        # 4. Restart the container
        docker_server.stop()

        # 5. Observe red indicator
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

        # Now restart the container
        docker_server.start()

        # Give the server a moment to be fully ready
        page.wait_for_timeout(10000)

        # 7. Refresh browser (standard F5/page.reload(), no cache wipe)
        page.reload()

        expect(page.get_by_text("Select a Connection").first).to_be_visible(
            timeout=5000
        )

        # 8. Observe indicators turn green
        local_health2 = page.locator(
            'div[data-label="local"] .connection-title span[id$="_health_local"]'
        )
        expect(local_health2).to_have_text("🟢", timeout=60000)

        page.screenshot(path="docs/qa-images/GEMWEBUI-265/reconnected.png")

        context.close()
        browser.close()
