import pytest
import time
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module")
def browser_context():
    with sync_playwright() as p:
        device = p.devices["Pixel 5"]
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
    # Since we enabled WebGL addon, the terminal is rendered on a canvas.
    # The font size is maintained within the `tab.term.options`

    initial_font_size = mobile_page.evaluate("""() => {
        const tabId = sessionStorage.getItem('gemini_active_tab');
        const tab = tabs.find(t => t.id === tabId);
        return tab.term.options.fontSize;
    }""")
    print(f"Initial font size: {initial_font_size}")

    # 2. Click A+
    mobile_page.click("text=A+", timeout=5000)
    # Wait for UI to react
    time.sleep(0.5)

    plus_font_size = mobile_page.evaluate("""() => {
        const tabId = sessionStorage.getItem('gemini_active_tab');
        const tab = tabs.find(t => t.id === tabId);
        return tab.term.options.fontSize;
    }""")
    print(f"Font size after A+: {plus_font_size}")
    assert plus_font_size > initial_font_size, "A+ should increase font size"

    # 3. Click A- twice
    mobile_page.click("text=A-", timeout=5000)
    time.sleep(0.1)
    mobile_page.click("text=A-", timeout=5000)
    time.sleep(0.5)

    minus_font_size = mobile_page.evaluate("""() => {
        const tabId = sessionStorage.getItem('gemini_active_tab');
        const tab = tabs.find(t => t.id === tabId);
        return tab.term.options.fontSize;
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
    mobile_page.evaluate(
        "window.sendToTerminalOriginal = window.sendToTerminal; window.lastSentData = null; window.sendToTerminal = (data) => { window.lastSentData = data; window.sendToTerminalOriginal(data); };"
    )

    # Test Tab button
    mobile_page.click("text=Tab")
    last_data = mobile_page.evaluate("window.lastSentData")
    assert last_data == "	", "Tab button should send 	"

    # Test Shift+Tab button
    mobile_page.click("text=Tab", modifiers=["Shift"])
    last_data = mobile_page.evaluate("window.lastSentData")
    assert last_data == "\x1b[Z", "Shift+Tab should send \\x1b[Z"

    # Test ▲ button (Esc[A)
    mobile_page.click("text=▲")
    last_data = mobile_page.evaluate("window.lastSentData")
    assert last_data == "\x1b[A", "Up arrow should send Esc[A"

    # Test Esc button
    mobile_page.click("text=Esc")
    last_data = mobile_page.evaluate("window.lastSentData")
    assert last_data == "\x1b", "Esc button should send Esc"


def test_haptic_feedback(mobile_page):
    """Verify that tapping extended keyboard controls triggers haptic feedback via navigator.vibrate."""
    # Mock navigator.vibrate
    mobile_page.evaluate("""() => {
        window.vibratedParams = [];
        navigator.vibrate = (pattern) => {
            window.vibratedParams.push(pattern);
            return true;
        };
    }""")

    # Test holdable button (Esc)
    esc_btn = mobile_page.locator("text=Esc")
    esc_btn.dispatch_event("touchstart")

    # Wait a bit
    time.sleep(0.1)

    # Check if navigator.vibrate was called
    vibrated_params = mobile_page.evaluate("window.vibratedParams")
    assert vibrated_params == [
        5
    ], f"Expected navigator.vibrate(5) to be called, got {vibrated_params}"

    esc_btn.dispatch_event("touchend")

    # Test toggle button (Ctrl)
    # Reset mock array
    mobile_page.evaluate("window.vibratedParams = []")

    ctrl_btn = mobile_page.locator("#ctrl-toggle")
    ctrl_btn.dispatch_event("touchstart")

    # Wait a bit
    time.sleep(0.1)

    vibrated_params = mobile_page.evaluate("window.vibratedParams")
    assert (
        vibrated_params == [5]
    ), f"Expected navigator.vibrate(5) to be called for Ctrl toggle, got {vibrated_params}"

    # Verify fallback (no JS error when navigator.vibrate is undefined)
    mobile_page.evaluate("""() => {
        window.vibratedParams = [];
        navigator.vibrate = undefined; // override
    }""")

    # Test holdable button again, shouldn't throw error
    esc_btn.dispatch_event("touchstart")

    # If we reached here without a crash, the test passes
    assert mobile_page.evaluate("window.vibratedParams.length") == 0


def test_haptic_feedback_hold_to_repeat(mobile_page):
    """Verify that holding a button triggers multiple haptic feedbacks at 5ms."""
    # Mock navigator.vibrate
    mobile_page.evaluate("""() => {
        window.vibratedParams = [];
        navigator.vibrate = (pattern) => {
            window.vibratedParams.push(pattern);
            return true;
        };
    }""")

    # Test holdable button (Esc)
    esc_btn = mobile_page.locator("text=Esc")
    esc_btn.dispatch_event("touchstart")

    # Wait for the hold-to-repeat delay (250ms) plus a few intervals (40ms each)
    time.sleep(0.4)

    # Stop the hold
    esc_btn.dispatch_event("touchend")

    # Check if navigator.vibrate was called multiple times
    vibrated_params = mobile_page.evaluate("window.vibratedParams")
    # First vibrate is on touchstart. Wait 250ms, then vibrate every 40ms.
    # Total wait is 400ms. 400 - 250 = 150ms. 150 / 40 = ~3-4 times.
    assert (
        len(vibrated_params) > 1
    ), f"Expected multiple haptic feedback events during hold, got {len(vibrated_params)}"
    assert all(
        p == 5 for p in vibrated_params
    ), f"Expected all vibrate patterns to be 5, got {vibrated_params}"
