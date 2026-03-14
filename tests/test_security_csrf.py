import pytest
import re
from src.app import app


def test_csrf_protection_missing_token(client):
    # Enable CSRF for this test
    app.config["WTF_CSRF_ENABLED"] = True

    # Try a state-changing operation without a CSRF token
    response = client.post(
        "/api/hosts", json={"label": "test_host", "target": "user@test"}
    )

    # Should fail with 400 Bad Request due to missing CSRF token
    assert response.status_code == 400
    assert (
        b'"csrf_expired":true' in response.data
        or b'"csrf_expired": true' in response.data
    )

    # Restore
    app.config["WTF_CSRF_ENABLED"] = False


def test_csrf_protection_with_token(client):
    app.config["WTF_CSRF_ENABLED"] = True

    # First, get the main page to extract the CSRF token from the meta tag
    response = client.get("/")
    assert response.status_code == 200

    # Extract the token using regex
    match = re.search(
        r'<meta name="csrf-token" content="([^"]+)">', response.data.decode("utf-8")
    )
    assert match is not None, "CSRF token meta tag not found"
    csrf_token = match.group(1)

    # Now try the state-changing operation with the token
    response = client.post(
        "/api/hosts",
        json={"label": "test_host", "target": "user@test"},
        headers={"X-CSRFToken": csrf_token},
    )

    # Should pass CSRF and be processed
    assert response.status_code in [200, 201]

    # Clean up
    client.delete("/api/hosts/test_host", headers={"X-CSRFToken": csrf_token})

    app.config["WTF_CSRF_ENABLED"] = False


def test_csrf_failure_returns_json_for_api(client):
    app.config["WTF_CSRF_ENABLED"] = True

    # Make a DELETE request to /api/management/sessions/123 with an invalid CSRF token
    response = client.delete(
        "/api/management/sessions/123", headers={"X-CSRFToken": "invalid-token"}
    )

    # Should fail with 400 Bad Request
    assert response.status_code == 400

    # Assert the Content-Type is application/json
    assert response.content_type == "application/json"

    # Assert the response body is valid JSON containing an "error" key
    data = response.get_json()
    assert data is not None
    assert "error" in data
    assert "CSRF token missing or incorrect" in data["error"]

    app.config["WTF_CSRF_ENABLED"] = False


def test_csrf_failure_returns_expired_flag(client):
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        "/api/hosts",
        json={"label": "test_host", "target": "user@test"},
        headers={"X-CSRFToken": "invalid-token"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data is not None
    assert "error" in data
    assert data.get("csrf_expired") is True

    app.config["WTF_CSRF_ENABLED"] = False


def test_csrf_socketio_rejection(client):
    app.config["WTF_CSRF_ENABLED"] = True

    from src.app import handle_connect

    try:
        with app.test_request_context("/"):
            # Missing CSRF
            with pytest.raises(ConnectionRefusedError, match="invalid_csrf"):
                handle_connect(auth={})

            # Invalid CSRF
            with pytest.raises(ConnectionRefusedError, match="invalid_csrf"):
                handle_connect(auth={"csrf_token": "bad-token"})
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


import os
import subprocess
import time
import signal
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def csrf_enabled_server_csrf(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    env["WTF_CSRF_ENABLED"] = "true"
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
def test_csrf_ui_hard_reload(csrf_enabled_server_csrf):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(csrf_enabled_server_csrf)

        # Wait for page to load
        btns = page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=5000)

        # Invalidate CSRF token in JS before connecting
        page.evaluate("""() => {
            const meta = document.querySelector('meta[name="csrf-token"]');
            if(meta) meta.setAttribute('content', 'bad-token');
        }""")

        # Start connection
        with page.expect_navigation(timeout=10000):
            btns.first.click()

        # After reload, session storage restores the tab. We should see a terminal instance.
        expect(
            page.locator(".tab-instance.active .terminal-instance").first
        ).to_be_visible(timeout=8000)

        context.close()
        browser.close()
