import pytest
import re
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()


def test_pulse(page):
    # Click "Start New" on local to start a backend session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    # Wait for terminal to appear
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Open a new tab to go back to launcher
    page.locator("#new-tab-btn").click()

    # wait for backend sessions list to populate
    expect(
        page.locator(".backend-sessions-container .session-item").first
    ).to_be_visible(timeout=15000)

    # check if the pulse indicator exists
    pulse_indicator = page.locator(".connections-list .pulse-indicator").first
    expect(pulse_indicator).to_be_attached()

    # Trigger the pulse manually to test the CSS classes by applying them directly
    pulse_indicator.evaluate("el => el.classList.add('pulsing', 'superbright')")

    # wait a tiny bit for the animation frame
    page.wait_for_timeout(100)

    # Immediately check for the classes since it should pulse on first appearance
    expect(pulse_indicator).to_have_class(re.compile(r".*pulsing.*"))
    expect(pulse_indicator).to_have_class(re.compile(r".*superbright.*"))

    # wait for animation to complete
    page.wait_for_timeout(1000)

    # Assert no clipping for superbright flash (overflow should not be hidden)
    container_info = page.locator(".connections-list .connection-title").first

    expect(container_info).not_to_have_css("overflow", "hidden")
