import pytest
import time
import subprocess
import os
import signal
import socket
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def authenticated_server(tmp_path, playwright):
    env = os.environ.copy()
    env["SECRET_KEY"] = "testsecret"
    env["ADMIN_USER"] = "testuser"
    env["ADMIN_PASS"] = "testpass"
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = str(s.getsockname()[1])
    env["PORT"] = port
    env["DATA_DIR"] = str(tmp_path)
    env["FLASK_USE_RELOADER"] = "false"
    env["SKIP_MONKEY_PATCH"] = "true"
    env["GEMWEBUI_HARNESS"] = "1"
    env["FLASK_DEBUG"] = "false"

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    mock_dir = os.path.join(project_root, "tests", "mock")
    env["PATH"] = f"{mock_dir}:{env.get('PATH', '')}"
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    process = subprocess.Popen(
        [python_bin, "src/app.py"],
        env=env,
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for port to open
    start_time = time.time()
    while time.time() - start_time < 30:
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


@pytest.mark.timeout(60)
def test_new_deployment_login(authenticated_server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    # Create a mobile context since bug affects mobile/safari often and it is a good test vector
    pixel = p.devices["Pixel 5"]
    context = browser.new_context(
        **pixel, http_credentials={"username": "testuser", "password": "testpass"}
    )
    page = context.new_page()

    js_errors = []
    page.on(
        "pageerror",
        lambda exc: js_errors.append(str(exc))
        if "dimensions" not in str(exc)
        else None,
    )
    page.on(
        "console",
        lambda msg: js_errors.append(msg.text)
        if msg.type == "error" and "dimensions" not in msg.text
        else None,
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

    page.wait_for_timeout(2000)

    # Click Start New on local
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
    if len(js_errors) > 0:
        print(f"DEBUG JS ERRORS: {js_errors}")
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

    context.close()
    browser.close()
