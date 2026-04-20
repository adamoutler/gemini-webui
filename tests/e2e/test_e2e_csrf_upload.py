import pytest
import os
import subprocess
import time
import signal
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def csrf_enabled_server(tmp_path, playwright):
    import os
    import shutil

    try:
        os.remove(os.path.join(str(tmp_path), "sessions.db"))
    except FileNotFoundError:
        pass
    shutil.rmtree(os.path.join(str(tmp_path), "workspace"), ignore_errors=True)
    os.makedirs(os.path.join(str(tmp_path), "workspace"), exist_ok=True)
    with open(
        os.path.join(str(tmp_path), "workspace", "gemini_mock_sessions.json"), "w"
    ) as f:
        f.write("[]")

    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    env["WTF_CSRF_ENABLED"] = "true"
    env["FLASK_USE_RELOADER"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = str(s.getsockname()[1])
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
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
    except Exception:
        pass


@pytest.mark.timeout(120)
def test_csrf_upload_over_ssh(csrf_enabled_server, tmp_path, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.set_default_timeout(60000)

    # We need to capture requests to see if CSRF token is present or rejected

    upload_requests = []
    page.on(
        "request",
        lambda request: upload_requests.append(request)
        if "/api/upload" in request.url
        else None,
    )

    # Capture console messages
    page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))

    page.goto(csrf_enabled_server)

    page.locator("#new-tab-btn").click()
    card = page.locator(".connection-card[data-label='local']").first
    btns = card.locator("button", has_text="Start New")
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=5000)
    page.wait_for_timeout(3000)

    # Open file transfer
    page.click('button:has-text("Files")')
    expect(page.locator("#file-transfer-modal")).to_be_visible(timeout=5000)

    test_file_path = os.path.join(tmp_path, "csrf_test_file.txt")
    with open(test_file_path, "w") as f:
        f.write("Test content for CSRF upload")

    page.locator("#workspace-upload-file").set_input_files(test_file_path)

    # Corrupt the token right before upload to simulate token expiration
    page.evaluate("""() => {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) meta.setAttribute('content', 'token_expired_123');
    }""")

    page.once("dialog", lambda dialog: dialog.accept())
    # accept any alerts (success or failure)

    with page.expect_response(
        lambda response: "/api/upload" in response.url and response.status == 200,
        timeout=15000,
    ) as response_info:
        page.click('button:has-text("Upload File")')

    resp = response_info.value
    assert resp is not None, "Upload API request should have been made"

    # X-CSRFToken header check
    req = resp.request
    csrf_header = req.headers.get("x-csrftoken")
    assert csrf_header, "CSRF Token missing from upload request headers!"

    # Verify response was not 400 Bad Request (CSRF failure)
    assert resp.status != 400, "CSRF validation failed on backend!"
    assert resp.status == 200, "Upload failed for another reason"

    context.close()
    browser.close()


@pytest.mark.timeout(120)
def test_csrf_drag_drop_upload_over_ssh(csrf_enabled_server, tmp_path, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.set_default_timeout(60000)

    upload_requests = []
    page.on(
        "request",
        lambda request: upload_requests.append(request)
        if "/api/upload" in request.url
        else None,
    )

    # Capture console messages
    page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))

    page.goto(csrf_enabled_server)

    page.locator("#new-tab-btn").click()
    card = page.locator(".connection-card[data-label='local']").first
    btns = card.locator("button", has_text="Start New")
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=5000)
    page.wait_for_timeout(3000)

    # Trigger dragover
    page.evaluate("""() => {
        const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.dispatchEvent(dragEvent);
    }""")

    expect(page.locator(".drop-zone")).to_have_class("drop-zone active", timeout=15000)

    with page.expect_response(
        lambda response: "/api/upload" in response.url and response.status == 200,
        timeout=15000,
    ) as response_info:
        # Trigger drop
        page.evaluate("""() => {
            const file = new File(["dropped content"], "drop_test_csrf.txt", { type: 'text/plain' });

            const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
            dropEvent.dataTransfer = {
                items: [
                    {
                        webkitGetAsEntry: () => ({
                            isFile: true,
                            isDirectory: false,
                            name: 'drop_test_csrf.txt',
                            file: (cb) => cb(file)
                        })
                    }
                ],
                files: [file]
            };
            document.dispatchEvent(dropEvent);
        }""")

    resp = response_info.value
    assert resp is not None, "Upload API request should have been made"

    req = resp.request
    csrf_header = req.headers.get("x-csrftoken")
    assert csrf_header, "CSRF Token missing from upload request headers!"

    assert resp.status != 400, "CSRF validation failed on backend!"
    assert resp.status == 200, "Upload failed for another reason"

    context.close()
    browser.close()
