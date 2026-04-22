import pytest
from playwright.sync_api import Page, expect


@pytest.mark.timeout(60)
def test_responsive_ui_desktop(page: Page, server):
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{server}/")

    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    page.click("text=Start New")
    page.wait_for_selector(".xterm-screen")

    page.wait_for_timeout(1000)
    mobile_controls = page.locator("#mobile-controls")

    # Take screenshot
    page.screenshot(path="docs/qa-images/responsive-desktop.png")

    # Verify it is not visible on desktop
    expect(mobile_controls).not_to_be_visible()


@pytest.mark.timeout(60)
def test_responsive_ui_mobile(playwright, server):
    device = playwright.devices["Pixel 5"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**device)
    page = context.new_page()

    page.goto(f"{server}/")

    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    page.click("text=Start New")
    page.wait_for_selector(".xterm-screen")

    page.wait_for_timeout(1000)
    mobile_controls = page.locator("#mobile-controls")

    # Take screenshot
    page.screenshot(path="docs/qa-images/responsive-mobile.png")

    # On mobile it should be visible
    expect(mobile_controls).to_be_visible()

    context.close()
    browser.close()
