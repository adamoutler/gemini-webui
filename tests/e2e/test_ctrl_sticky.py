# Resolves Tickets GEMWEBUI-174, GEMWEBUI-175
import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module")
def browser_context(playwright):
    playwright = playwright
    if True:
        device = playwright.devices["Pixel 5"]
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(**device)
        yield context
        context.close()
        browser.close()


@pytest.fixture(scope="function")
def mobile_page(server, browser_context):
    page = browser_context.new_page()
    page.set_default_timeout(60000)
    page.goto(server, timeout=15000)
    # Start a local session to see controls
    page.locator("#new-tab-btn").click()
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)
    # Wait for controls to be visible on mobile
    expect(page.locator("#mobile-controls")).to_be_visible(timeout=15000)
    yield page
    page.close()


def test_ctrl_sticky(mobile_page):
    # Tap Ctrl button (not holding it)
    ctrl_btn = mobile_page.locator("#ctrl-toggle")

    # Tapping using simple click
    ctrl_btn.click()

    expect(ctrl_btn).to_have_class("control-btn active")

    # Now type 'c' in the terminal
    # Find the active tab ID
    active_tab_id = mobile_page.evaluate("sessionStorage.getItem('gemini_active_tab')")
    textarea = mobile_page.locator(".mobile-text-area")

    textarea.evaluate(
        "el => { el.value = 'c'; el.dispatchEvent(new Event('input', { bubbles: true })); }"
    )

    # Now let's see if ctrlActive was applied.
    # If applied, the terminal should have sent \x03
    # Let's check the active state of ctrl_btn - it should be cleared!
    expect(ctrl_btn).not_to_have_class("control-btn active", timeout=15000)
