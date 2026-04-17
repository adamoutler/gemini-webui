import pytest
import os
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module")
def browser_context(playwright):
    playwright = playwright
    device = playwright.devices["Pixel 5"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**device)
    yield context
    context.close()
    browser.close()


@pytest.fixture(scope="function")
def mobile_page(server, browser_context, playwright):
    page = browser_context.new_page()
    page.goto(server, timeout=15000)
    # Start a local session to see controls
    page.locator("#new-tab-btn").click()
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=5000)
    # Wait for controls to be visible on mobile
    expect(page.locator("#mobile-controls")).to_be_visible(timeout=5000)

    # Ensure there is a terminal created and visible
    # On mobile, the native textarea is disabled, so wait for proxy input instead
    page.wait_for_selector(".mobile-text-area", state="attached", timeout=5000)
    yield page
    page.close()


def test_modifier_keyboard_focus(mobile_page, playwright):
    # Tap Ctrl button using mobile touch event
    ctrl_btn = mobile_page.locator("#ctrl-toggle")

    # We want to explicitly simulate a mobile touch
    ctrl_btn.tap()

    expect(ctrl_btn).to_have_class("control-btn active")

    # Get active tab ID
    active_tab_id = mobile_page.evaluate("sessionStorage.getItem('gemini_active_tab')")

    # Evaluate what the active element is right after tapping Ctrl
    is_textarea_focused, active_id = mobile_page.evaluate("""() => {
        const activeElement = document.activeElement;
        const textarea = document.querySelector(".mobile-text-area");
        return [activeElement === textarea, activeElement ? activeElement.id || activeElement.tagName : "none"];
    }""")

    assert (
        is_textarea_focused is True
    ), f"The terminal hidden textarea was not immediately focused upon tapping a modifier button. Instead focused: {active_id}"

    # Let's test Alt as well
    alt_btn = mobile_page.locator("#alt-toggle")
    alt_btn.tap()
    expect(alt_btn).to_have_class("control-btn active")

    is_textarea_focused_alt = mobile_page.evaluate("""() => {
        const activeElement = document.activeElement;
        const textarea = document.querySelector(".mobile-text-area");
        return activeElement === textarea;
    }""")

    assert (
        is_textarea_focused_alt is True
    ), "The terminal hidden textarea was not immediately focused upon tapping Alt."

    screenshot_path = f"/tmp/gemwe-182_{os.environ.get('BUILD_NUMBER', 'local')}.png"
    mobile_page.screenshot(path=screenshot_path)
    print(
        f"EVIDENCE: The hidden textarea is focused/on-screen keyboard is triggered. Screenshot saved to {screenshot_path}"
    )
