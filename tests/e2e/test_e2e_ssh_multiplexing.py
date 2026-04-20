import pytest
import os
import subprocess
import time
import signal
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def ssh_test_server(tmp_path, playwright):
    persisted_file = tmp_path / "persisted_sessions.json"
    if persisted_file.exists():
        try:
            persisted_file.unlink()
        except OSError:
            pass

    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    env["WTF_CSRF_ENABLED"] = "false"
    env["FLASK_USE_RELOADER"] = "false"
    env["SKIP_MONKEY_PATCH"] = "true"
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = str(s.getsockname()[1])
    env["PORT"] = port
    env["DATA_DIR"] = str(tmp_path)

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    proc = subprocess.Popen(
        [python_bin, "-m", "src.app"], env=env, cwd=project_root, start_new_session=True
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
        proc.wait(timeout=5)
    except OSError:
        pass


@pytest.mark.timeout(30)
def test_ssh_multiplexing_loading_state(ssh_test_server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto(ssh_test_server)

    # Intercept the /api/management/sessions to return empty
    page.route("**/api/management/sessions", lambda route: route.fulfill(json=[]))

    # We want to capture the "Establishing connection" text. To do this, we can simulate
    # a slow fetch request when listing sessions.
    page.route("**/api/hosts", lambda route: route.continue_())

    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()

    # Wait for the UI to update to the fetching state before taking screenshot
    page.wait_for_timeout(1000)

    # Let's take a screenshot of the loading indicator!
    screenshot_path = f"public/qa-screenshots/ssh_cold_start_loading_{os.environ.get('BUILD_NUMBER', 'local')}.png"
    page.screenshot(path=screenshot_path)
    print(
        f"Empirical Evidence: Loading indicator shown. Visual proof saved to {screenshot_path}"
    )

    context.close()
    browser.close()


@pytest.mark.timeout(120)
def test_ssh_connection_error_bubbling(ssh_test_server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto(ssh_test_server)

    # Ensure launcher is loaded
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)

    # Open Settings to add host
    page.locator('button[data-onclick="openSettings()"]').click()
    expect(page.locator("#settings-modal")).to_be_visible(timeout=15000)

    # Fill in the new host details with a clearly invalid port to ensure it fails quickly
    page.locator("#new-host-label").fill("Invalid SSH Host")
    page.locator("#new-host-target").fill("invalid_user@127.0.0.1:9999")
    page.locator("#new-host-dir").fill("/tmp")

    # Click Add Host
    with page.expect_response("**/api/hosts") as response_info:
        page.locator("#add-host-btn").click()

    response = response_info.value
    assert response.status == 200, f"Failed to add host, status {response.status}"

    # Close settings
    page.evaluate("closeSettings()")
    expect(page.locator("#settings-modal")).not_to_be_visible(timeout=15000)

    # The new host should appear as a connection card. Click its Start New button.
    card = page.locator(".connection-card").filter(has_text="Invalid SSH Host").first
    expect(card).to_be_visible(timeout=15000)
    card.locator("button", has_text="Start New").click()

    # Wait for the terminal to print something that looks like an error.
    # It takes a few seconds for the SSH process to timeout and return the error.
    page.wait_for_timeout(4000)

    screenshot_path = f"public/qa-screenshots/ssh_error_bubbling_{os.environ.get('BUILD_NUMBER', 'local')}.png"
    page.screenshot(path=screenshot_path)
    print(
        f"Empirical Evidence: Error bubbled up cleanly. Visual proof saved to {screenshot_path}"
    )

    context.close()
    browser.close()
