import pytest
import time
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="module")
def browser_context():
    with sync_playwright() as p:
        device = p.devices['Pixel 5']
        browser = p.chromium.launch(headless=True)
        # Use a single context for the whole module to save time
        context = browser.new_context(**device)
        yield context
        context.close()
        browser.close()

@pytest.fixture(scope="function")
def mobile_page(server, browser_context):
    page = browser_context.new_page()
    page.goto(server, timeout=15000)
    # Start a local session to see controls
    page.click("text=Start New", timeout=10000)
    page.wait_for_selector("#mobile-controls", state="visible", timeout=10000)
    yield page
    page.close()

def test_font_size_controls(mobile_page):
    """Verify A+ and A- buttons adjust terminal font size."""
    # 1. Get initial font size
    initial_font_size = mobile_page.evaluate("""() => {
        const tabId = sessionStorage.getItem('gemini_active_tab');
        // We can't easily access the internal 'tabs' array from here, 
        // but we can check the computed style of the terminal rows.
        const row = document.querySelector('.xterm-rows div');
        return parseInt(window.getComputedStyle(row).fontSize);
    }""")
    print(f"Initial font size: {initial_font_size}")

    # 2. Click A+
    mobile_page.click("text=A+", timeout=5000)
    # Wait for UI to react
    time.sleep(0.5)

    plus_font_size = mobile_page.evaluate("""() => {
        const row = document.querySelector('.xterm-rows div');
        return parseInt(window.getComputedStyle(row).fontSize);
    }""")
    print(f"Font size after A+: {plus_font_size}")
    assert plus_font_size > initial_font_size, "A+ should increase font size"

    # 3. Click A- twice
    mobile_page.click("text=A-", timeout=5000)
    time.sleep(0.1)
    mobile_page.click("text=A-", timeout=5000)
    time.sleep(0.5)

    minus_font_size = mobile_page.evaluate("""() => {
        const row = document.querySelector('.xterm-rows div');
        return parseInt(window.getComputedStyle(row).fontSize);
    }""")
    print(f"Font size after A- x2: {minus_font_size}")
    assert minus_font_size < plus_font_size, "A- should decrease font size"

def test_ctrl_alt_toggles(mobile_page):
    """Verify Ctrl and Alt buttons toggle active state."""
    ctrl_btn = mobile_page.locator("#ctrl-toggle")
    alt_btn = mobile_page.locator("#alt-toggle")

    # Initial state
    expect(ctrl_btn).not_to_have_class("active")
    expect(alt_btn).not_to_have_class("active")

    # Toggle Ctrl
    ctrl_btn.click()
    expect(ctrl_btn).to_have_class("control-btn active")

    # Toggle Alt
    alt_btn.click()
    expect(alt_btn).to_have_class("control-btn active")

    # Toggle Ctrl off
    ctrl_btn.click()
    expect(ctrl_btn).not_to_have_class("active")
    # Alt should still be active
    expect(alt_btn).to_have_class("control-btn active")

def test_holdable_buttons_emit_commands(mobile_page):
    """Verify that buttons with data-cmd emit commands to the terminal."""
    # This is harder to test directly without checking socket output,
    # but we can verify they don't throw JS errors and maybe check if xterm reacts.
    
    # We'll use a mock to see if 'sendToTerminal' is called
    mobile_page.evaluate("window.sendToTerminalOriginal = window.sendToTerminal; window.lastSentData = null; window.sendToTerminal = (data) => { window.lastSentData = data; window.sendToTerminalOriginal(data); };")
    
    # Test Tab button
    mobile_page.click("text=Tab")
    last_data = mobile_page.evaluate("window.lastSentData")
    assert last_data == "	", "Tab button should send 	"

    # Test ▲ button (Esc[A)
    mobile_page.click("text=▲")
    last_data = mobile_page.evaluate("window.lastSentData")
    assert last_data == "\x1b[A", "Up arrow should send Esc[A"

    # Test Esc button
    mobile_page.click("text=Esc")
    last_data = mobile_page.evaluate("window.lastSentData")
    assert last_data == "\x1b", "Esc button should send Esc"
