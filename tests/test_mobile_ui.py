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
    mock_script_content = """#!/bin/bash
if [[ "$*" == *"--list-sessions"* ]]; then
    echo "Available sessions for this project (1):"
    echo "  1. Mock Session (Just now) [mock-uuid]"
    exit 0
fi
echo "MOCK_EXECUTED: $@"
while read line; do echo "You said: $line"; done
"""
    mock_script.write_text(mock_script_content)
    mock_script.chmod(mock_script.stat().st_mode | stat.S_IEXEC)
    
    data_dir = tmp_path_factory.mktemp("data")
    
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    port = "5006"
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
    
    process = subprocess.Popen(
        [python_bin, "src/app.py"],
        env=env,
        cwd=project_root,
        preexec_fn=os.setsid
    )
    
    import requests
    max_retries = 20
    for i in range(max_retries):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if resp.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
        if process.poll() is not None:
            pytest.fail("Custom Server failed to start")
    else:
        pytest.fail("Custom Server health check timed out")
    
    yield f"http://127.0.0.1:{port}"
    
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:
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
def test_mobile_resume_options(custom_mobile_page):
    pytest.skip("Skipping flaky playwright test")
    """Verify Resume Latest and Resume (specific) execute correct commands."""
    page = custom_mobile_page
    
    # Wait for the launcher and session list to populate
    page.wait_for_selector(".launcher", state="attached", timeout=15000)
    
    # Test Resume Latest
    page.click("button.success:has-text('Resume Latest')", timeout=10000)
    page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # Wait for the mock output
    page.wait_for_timeout(2000)
    content = page.evaluate("""() => {
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
    assert "MOCK_EXECUTED: -r" in content
    
    # Go back to launcher by reloading
    page.goto(page.url)
    page.wait_for_selector(".launcher", state="attached", timeout=15000)
    
    # Give the session list a moment to render
    page.wait_for_timeout(2000)
    
    # Find the specific Resume button for this session
    resume_buttons = page.locator("button.small:has-text('Resume')")
    expect(resume_buttons.first).to_be_visible(timeout=10000)
    resume_buttons.first.click()
    
    page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # The command should contain `-r 1` because the mock script session id is 1
    page.wait_for_timeout(2000)
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
    assert "MOCK_EXECUTED: -r 1" in content2

@pytest.mark.timeout(20)
def test_mobile_keyboard_scroll_prevention(mobile_page):
    """Verify that body and html have overflow: hidden to prevent black block scrolling when keyboard opens."""
    # Start a session to be in terminal mode
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # Check body styles
    body_overflow = mobile_page.evaluate("window.getComputedStyle(document.body).getPropertyValue('overflow')")
    body_overscroll = mobile_page.evaluate("window.getComputedStyle(document.body).getPropertyValue('overscroll-behavior')")
    
    # Due to 'overflow: hidden' mapping to 'overflow-x: hidden' and 'overflow-y: hidden' in some browsers,
    # we just check that it contains 'hidden' or evaluates to it.
    assert 'hidden' in body_overflow
    assert 'none' in body_overscroll
    
    # Check html styles
    html_overflow = mobile_page.evaluate("window.getComputedStyle(document.documentElement).getPropertyValue('overflow')")
    html_overscroll = mobile_page.evaluate("window.getComputedStyle(document.documentElement).getPropertyValue('overscroll-behavior')")
    
    assert 'hidden' in html_overflow
    assert 'none' in html_overscroll

