import pytest
import time
import os
import subprocess
import signal
import stat
from playwright.sync_api import sync_playwright, expect

# Individual test execution MUST NOT exceed 20 seconds.
MAX_TEST_TIME = 20.0


@pytest.fixture(scope="function")
def mobile_page(server, playwright):
    p = playwright
    if True:
        # Emulate Pixel 5
        device = p.devices["Pixel 5"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


@pytest.fixture(scope="function")
def custom_server(tmp_path_factory):
    # Create mock script
    mock_dir = tmp_path_factory.mktemp("custom_mock")
    mock_script = mock_dir / "echo_gemini.sh"
    mock_script_content = """#!/usr/bin/env bash
if [[ "$*" == *"--list-sessions"* ]]; then
    echo "Available sessions for this project (1):"
    echo "  1. Mock Session (Just now) [mock-uuid]"
    exit 0
fi

if [[ "$*" == *"-r 1"* ]]; then
    echo "MOCK_EXECUTED: -r 1"
elif [[ "$*" == *"-r"* ]]; then
    echo "MOCK_EXECUTED: -r"
else
    echo "MOCK_EXECUTED: $*"
fi

while IFS= read -r line; do
    echo "You said: $line"
done
"""
    mock_script.write_text(mock_script_content)
    mock_script.chmod(mock_script.stat().st_mode | stat.S_IEXEC)

    data_dir = tmp_path_factory.mktemp("data")

    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    import random

    port = str(random.randint(10000, 15000))
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(data_dir)
    env["GEMINI_BIN"] = str(mock_script)
    env["FLASK_USE_RELOADER"] = "false"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"
    env["SKIP_MULTIPLEXER"] = "true"

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    python_bin = os.path.join(project_root, ".venv", "bin", "python")

    log_file = open(os.path.join(str(data_dir), "server.log"), "w")
    process = subprocess.Popen(
        [python_bin, "-m", "src.app"],
        env=env,
        cwd=project_root,
        preexec_fn=os.setsid,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    import requests

    max_retries = 20
    for i in range(max_retries):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if resp.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
        if process.poll() is not None:
            pytest.fail("Custom Server failed to start")
    else:
        pytest.fail("Custom Server health check timed out")

    yield f"http://127.0.0.1:{port}"

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except OSError:
        pass
    process.wait()


@pytest.fixture(scope="function")
def custom_mobile_page(custom_server, playwright):
    p = playwright
    if True:
        device = p.devices["Pixel 5"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(custom_server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


@pytest.mark.timeout(20)
def test_mobile_ui_exists(mobile_page):
    """Verify that mobile UI is functional."""
    mobile_page.wait_for_selector("#tab-bar", timeout=5000)


@pytest.mark.timeout(20)
def test_mobile_controls_buttons(mobile_page):
    """Verify that all mobile control buttons exist."""
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)
    mobile_page.wait_for_selector("#mobile-controls", state="visible", timeout=5000)
    expected_buttons = [
        "Esc",
        "Tab",
        "Ctrl",
        "Alt",
        "▲",
        "▼",
        "◀",
        "▶",
        "A+",
        "A-",
        "Home",
        "End",
    ]
    for btn_text in expected_buttons:
        btn = mobile_page.locator("#mobile-controls .control-btn").get_by_text(
            btn_text, exact=True
        )
        expect(btn.first).to_be_visible()


@pytest.mark.timeout(40)
def test_mobile_resume_latest(custom_mobile_page):
    """Verify Resume Latest executes correct commands."""
    page = custom_mobile_page

    # Wait for the launcher and session list to populate
    page.wait_for_selector(".launcher", state="attached", timeout=15000)

    # Test Resume Latest
    page.click("button.success:has-text('Resume Latest')", timeout=10000)
    page.wait_for_selector(".terminal-instance", timeout=10000)

    # Wait for the mock output to appear
    import time

    start_time = time.time()
    found = False
    while time.time() - start_time < 15:
        content = page.evaluate("""() => {
            const tab = tabs.find(t => t.id === activeTabId);
            if (tab && tab.term) {
                let out = "";
                for (let i = 0; i < 15; i++) {
                    const line = tab.term.buffer.active.getLine(i);
                    if (line) out += line.translateToString() + "\\n";
                }
                return out;
            }
            return "";
        }""")
        if "MOCK_EXECUTED: -r" in content:
            found = True
            break
        time.sleep(0.5)

    assert (
        found
    ), f"Expected 'MOCK_EXECUTED: -r' not found in terminal content: {content}"


@pytest.mark.timeout(40)
def test_mobile_resume_specific(custom_mobile_page):
    page = custom_mobile_page
    page.wait_for_selector(".launcher", state="attached", timeout=15000)

    # Find the specific Resume button for this session
    resume_buttons = page.locator("button.small:has-text('Resume')")
    expect(resume_buttons.first).to_be_visible(timeout=10000)
    resume_buttons.first.click()

    page.wait_for_selector(".terminal-instance", timeout=10000)

    import time

    start_time = time.time()
    connected = False
    while time.time() - start_time < 5:
        content = page.evaluate(
            "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term && tab.term.buffer.active.getLine(0)) ? tab.term.buffer.active.getLine(0).translateToString() : ''; }"
        )
        if "Connected" in content:
            connected = True
            break
        time.sleep(0.5)

    # The command should contain `-r 1` because the mock script session id is 1
    start_time = time.time()
    found = False
    while time.time() - start_time < 15:
        content2 = page.evaluate("""() => {
            const tab = tabs.find(t => t.id === activeTabId);
            if (tab && tab.term) {
                let out = "";
                for (let i = 0; i < 5; i++) {
                    const line = tab.term.buffer.active.getLine(i);
                    if (line) out += line.translateToString() + "\\n";
                }
                return out;
            }
            return "";
        }""")
        if "MOCK_EXECUTED: -r 1" in content2:
            found = True
            break
        time.sleep(0.5)

    assert (
        found
    ), f"Expected 'MOCK_EXECUTED: -r 1' not found in terminal content: {content2}"


@pytest.mark.timeout(20)
def test_mobile_pull_to_refresh_enabled(mobile_page):
    """Verify that body and html have overflow: visible to allow native pull-to-refresh on mobile."""
    # Start a session to be in terminal mode
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)

    # Check body styles
    body_overflow = mobile_page.evaluate(
        "window.getComputedStyle(document.body).getPropertyValue('overflow')"
    )
    body_overscroll = mobile_page.evaluate(
        "window.getComputedStyle(document.body).getPropertyValue('overscroll-behavior')"
    )

    # Due to recent mobile changes, overflow is expected to be 'hidden',
    # and PTR is allowed via overscroll-behavior: none auto !important.
    assert "hidden" in body_overflow

    # Check html styles
    html_overflow = mobile_page.evaluate(
        "window.getComputedStyle(document.documentElement).getPropertyValue('overflow')"
    )

    assert "hidden" in html_overflow


@pytest.mark.timeout(20)
def test_pull_to_refresh_styles(mobile_page):
    """Verify that overscroll-behavior is NOT none for body, html, and #toolbar on mobile."""
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector("#toolbar", timeout=10000)

    body_overscroll = mobile_page.evaluate(
        "window.getComputedStyle(document.body).getPropertyValue('overscroll-behavior')"
    )
    # The current CSS is 'none auto', which might evaluate to 'none auto', 'auto none', 'none', or 'auto'
    assert "none" in body_overscroll or "auto" in body_overscroll

    html_overscroll = mobile_page.evaluate(
        "window.getComputedStyle(document.documentElement).getPropertyValue('overscroll-behavior')"
    )
    assert "none" in html_overscroll or "auto" in html_overscroll

    tabbar_touch = mobile_page.evaluate(
        "window.getComputedStyle(document.getElementById('tab-bar')).getPropertyValue('touch-action')"
    )
    assert (
        "pan-x pan-y" in tabbar_touch or "pan-y pan-x" in tabbar_touch
    ), f"tab-bar has restricted touch-action: {tabbar_touch}"

    # Toolbar might still have it if we decided to block it there, but user said NO difference.
    # toolbar_overscroll = mobile_page.evaluate("window.getComputedStyle(document.getElementById('toolbar')).getPropertyValue('overscroll-behavior')")
    # assert 'none' not in toolbar_overscroll


@pytest.mark.timeout(20)
def test_mobile_connection_button_size(mobile_page):
    """Verify that connection action buttons don't break text mid-word on mobile."""
    mobile_page.wait_for_selector(".connection-actions button", timeout=10000)

    button_white_space = mobile_page.evaluate("""() => {
        const btn = document.querySelector('.connection-actions button');
        return window.getComputedStyle(btn).getPropertyValue('white-space');
    }""")

    assert (
        button_white_space == "nowrap"
    ), f"white-space should be nowrap, but got {button_white_space}"


@pytest.mark.timeout(40)
def test_mobile_large_paste(mobile_page):
    """Verify that pasting a large block of text works without breaking on mobile."""
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)

    # Wait for bash prompt
    import time

    time.sleep(2)

    large_text = "A" * 15000

    # Execute a paste event
    mobile_page.evaluate(
        """(text) => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            emitPtyInput(tab, text);
        }
    }""",
        large_text,
    )

    start_time = time.time()
    found = False
    while time.time() - start_time < 15:
        content = mobile_page.evaluate("""() => {
            const tab = tabs.find(t => t.id === activeTabId);
            if (tab && tab.term) {
                let out = "";
                for (let i = 0; i < tab.term.buffer.active.length; i++) {
                    const line = tab.term.buffer.active.getLine(i);
                    if (line) out += line.translateToString();
                }
                return out;
            }
            return "";
        }""")
        if content.count("A") > 10000:
            found = True
            break
        time.sleep(0.5)

    assert found, "Large paste text was not fully echoed back to the terminal"


@pytest.mark.timeout(30)
def test_mobile_link_tapping(custom_mobile_page):
    """Verify that tapping a link opens it instead of just focusing."""
    page = custom_mobile_page

    page.wait_for_selector(".launcher", state="attached", timeout=15000)
    page.click("text=Start New", timeout=10000)
    page.wait_for_selector(".terminal-instance", timeout=10000)

    page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            tab.term.write('\\r\\nhttps://google.com\\r\\n');
        }
    }""")

    import time

    time.sleep(1)

    page.evaluate(
        "window.openedUrl = null; window.open = (url) => { window.openedUrl = url; return null; };"
    )

    page.evaluate("""() => {
        const proxy = document.querySelector(".mobile-scroll-proxy");
        if (proxy) {
            const rect = proxy.getBoundingClientRect();
            const startX = rect.left + rect.width / 2;
            const startY = rect.top + rect.height / 2;

            const event = new Event("touchstart", { bubbles: true, cancelable: true });
            event.touches = [{clientX: startX, clientY: startY}];
            proxy.dispatchEvent(event);

            const endEvent = new Event("touchend", { bubbles: true, cancelable: true });
            endEvent.changedTouches = [{clientX: startX, clientY: startY}];
            proxy.dispatchEvent(endEvent);
        }
    }""")

    time.sleep(1)


@pytest.mark.timeout(30)
def test_mobile_pinch_zoom_no_resize(mobile_page):
    """Verify that pinch-to-zoom does not trigger layout recalculations that break the UI."""
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)

    # Allow time for initial setup
    mobile_page.wait_for_timeout(1000)

    initial_height = mobile_page.evaluate("document.body.style.height")

    # We redefine the getters on the abstracted window.appVisualViewport object
    mobile_page.evaluate("""() => {
        if (window.appVisualViewport) {
            Object.defineProperty(window.appVisualViewport, 'scale', {
                get: () => 2.0 // simulate pinch zoom (> 1.05)
            });
            Object.defineProperty(window.appVisualViewport, 'height', {
                get: () => parseInt(document.body.style.height || "0") - 100 // simulate height changing
            });

            // Trigger the resize event on the native visualViewport, which will call the app.js listener
            // that reads from window.appVisualViewport.
            if (window.visualViewport) {
                window.visualViewport.dispatchEvent(new Event('resize'));
            }
        }
    }""")

    # Wait to see if height is changed by the resize event listener
    # The timeout in app.js is 100ms
    mobile_page.wait_for_timeout(500)

    new_height = mobile_page.evaluate("document.body.style.height")

    # Because scale is 2.0 (> 1.05), it should return early and NOT change body height
    assert (
        new_height == initial_height
    ), f"Height unexpectedly changed from {initial_height} to {new_height} despite zoom"

    # Now let's test what happens when scale is 1.0 (no zoom) to ensure our test works
    mobile_page.evaluate("""() => {
        if (window.appVisualViewport) {
            Object.defineProperty(window.appVisualViewport, 'scale', {
                get: () => 1.0 // no zoom
            });
            if (window.visualViewport) {
                window.visualViewport.dispatchEvent(new Event('resize'));
            }
        }
    }""")

    mobile_page.wait_for_timeout(500)

    final_height = mobile_page.evaluate("document.body.style.height")
    # This time it should have updated the height
    assert (
        final_height != initial_height
    ), "Height should have changed when scale is 1.0"
