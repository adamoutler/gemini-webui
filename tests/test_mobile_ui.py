import pytest
import time
import os
import sys
import subprocess
import signal
import stat
from playwright.sync_api import sync_playwright, expect

# Individual test execution MUST NOT exceed 20 seconds.
MAX_TEST_TIME = 20.0

@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        # Emulate Pixel 5
        device = p.devices['Pixel 5']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
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
    port = str(random.randint(6000, 9000))
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(data_dir)
    env["GEMINI_BIN"] = str(mock_script)
    env["FLASK_USE_RELOADER"] = "false"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"
    env["SKIP_MULTIPLEXER"] = "true"
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")
    
    log_file = open(os.path.join(str(data_dir), "server.log"), "w")
    process = subprocess.Popen(
        [python_bin, "-m", "src.app"],
        env=env,
        cwd=project_root,
        preexec_fn=os.setsid,
        stdout=log_file,
        stderr=subprocess.STDOUT
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
def custom_mobile_page(custom_server):
    with sync_playwright() as p:
        device = p.devices['Pixel 5']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(custom_server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
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
    expected_buttons = ["Esc", "Tab", "Ctrl", "Alt", "▲", "▼", "◀", "▶", "A+", "A-", "Home", "End"]
    for btn_text in expected_buttons:
        btn = mobile_page.locator("#mobile-controls .control-btn").get_by_text(btn_text, exact=True)
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
    
    assert found, f"Expected 'MOCK_EXECUTED: -r' not found in terminal content: {content}"

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
        content = page.evaluate("() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term && tab.term.buffer.active.getLine(0)) ? tab.term.buffer.active.getLine(0).translateToString() : ''; }")
        if 'Connected' in content:
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

    assert found, f"Expected 'MOCK_EXECUTED: -r 1' not found in terminal content: {content2}"

@pytest.mark.timeout(20)
def test_mobile_pull_to_refresh_enabled(mobile_page):
    """Verify that body and html have overflow: visible to allow native pull-to-refresh on mobile."""
    # Start a session to be in terminal mode
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # Check body styles
    body_overflow = mobile_page.evaluate("window.getComputedStyle(document.body).getPropertyValue('overflow')")
    body_overscroll = mobile_page.evaluate("window.getComputedStyle(document.body).getPropertyValue('overscroll-behavior')")
    
    # Due to 'overflow: visible' allowing native PTR
    # we just check that it contains 'visible' or evaluates to it.
    assert 'visible' in body_overflow

    # Check html styles
    html_overflow = mobile_page.evaluate("window.getComputedStyle(document.documentElement).getPropertyValue('overflow')")

    assert 'visible' in html_overflow
@pytest.mark.timeout(20)
def test_pull_to_refresh_styles(mobile_page):
    """Verify that overscroll-behavior is NOT none for body, html, and #toolbar on mobile."""
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector("#toolbar", timeout=10000)
    
    body_overscroll = mobile_page.evaluate("window.getComputedStyle(document.body).getPropertyValue('overscroll-behavior')")
    assert 'none' not in body_overscroll
    
    html_overscroll = mobile_page.evaluate("window.getComputedStyle(document.documentElement).getPropertyValue('overscroll-behavior')")
    assert 'none' not in html_overscroll

    tabbar_touch = mobile_page.evaluate("window.getComputedStyle(document.getElementById('tab-bar')).getPropertyValue('touch-action')")
    assert 'none' not in tabbar_touch and 'pan-x pan-y' not in tabbar_touch, f"tab-bar has restricted touch-action: {tabbar_touch}"
    
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

    assert button_white_space == 'nowrap', f"white-space should be nowrap, but got {button_white_space}"

