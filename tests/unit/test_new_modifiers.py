import pytest
import time
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module")
def browser_context(playwright):
    p = playwright
    device = p.devices["Pixel 5"]
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(**device)
    yield context
    context.close()
    browser.close()


@pytest.fixture(scope="function")
def mobile_page(server, browser_context):
    page = browser_context.new_page()
    page.goto(server, timeout=15000)
    try:
        page.wait_for_selector("#mobile-controls", state="visible", timeout=2000)
    except Exception:
        page.click("text=Start New", timeout=10000)
        page.wait_for_selector("#mobile-controls", state="visible", timeout=10000)
    yield page
    page.close()


@pytest.mark.timeout(60)
def test_new_modifier_toggles_existence(mobile_page):
    """Verify Shift and Super buttons exist and toggle active state."""
    shift_btn = mobile_page.locator("#shift-toggle")
    super_btn = mobile_page.locator("#super-toggle")

    expect(shift_btn).to_be_visible()
    expect(super_btn).to_be_visible()

    # Capture screenshot for visual proof
    mobile_page.screenshot(path="docs/qa-images/mobile_new_modifiers_layout.png")

    # Toggle Shift
    shift_btn.click()
    expect(shift_btn).to_have_class("control-btn active")

    mobile_page.screenshot(path="docs/qa-images/mobile_shift_active.png")

    # Toggle Super
    super_btn.click()
    expect(super_btn).to_have_class("control-btn active")

    mobile_page.screenshot(path="docs/qa-images/mobile_super_active.png")

    # Toggle Shift off
    shift_btn.click()
    expect(shift_btn).not_to_have_class("active")
    expect(super_btn).to_have_class("control-btn active")


@pytest.mark.timeout(60)
def test_super_z_undo(mobile_page):
    """Verify that Super toggle + 'z' sends Alt+Z sequence for undo."""
    mobile_page.evaluate(
        "window.lastSentData = null; window.emitPtyInput = (tab, data) => { window.lastSentData = data; };"
    )

    super_btn = mobile_page.locator("#super-toggle")

    # 1. Tap Super toggle
    super_btn.click()
    expect(super_btn).to_have_class("control-btn active")

    # 2. Type 'z' in the proxy input
    textarea = mobile_page.locator(".mobile-text-area")
    textarea.focus()

    # Use press instead of type to ensure all events are fired
    textarea.press("z")

    # We might need a small delay for input handling
    time.sleep(1)

    # 3. Verify sequence (should be \x1b z)
    last_data = mobile_page.evaluate("window.lastSentData")
    assert (
        last_data == "\x1bz"
    ), f"Expected Alt+Z sequence (\\x1bz), got {repr(last_data)}"

    # 4. Verify Super toggle is cleared
    expect(super_btn).not_to_have_class("active")


@pytest.mark.timeout(60)
def test_shift_tab_toggle(mobile_page):
    """Verify that Shift toggle + Tab button sends Shift+Tab sequence."""
    mobile_page.evaluate(
        "window.lastSentData = null; window.emitPtyInput = (tab, data) => { window.lastSentData = data; };"
    )

    shift_btn = mobile_page.locator("#shift-toggle")
    tab_btn = mobile_page.locator(".holdable:has-text('Tab')").first

    # 1. Tap Shift toggle
    shift_btn.click()
    expect(shift_btn).to_have_class("control-btn active")

    # 2. Tap Tab button
    tab_btn.dispatch_event("touchstart")
    time.sleep(0.1)
    tab_btn.dispatch_event("touchend")

    # 3. Verify sequence
    last_data = mobile_page.evaluate("window.lastSentData")
    assert (
        last_data == "\x1b[Z"
    ), f"Expected Shift+Tab sequence (\\x1b[Z), got {repr(last_data)}"

    # 4. Verify Shift toggle is cleared
    expect(shift_btn).not_to_have_class("active")
