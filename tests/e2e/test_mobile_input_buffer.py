import pytest
from playwright.sync_api import expect


@pytest.mark.timeout(60)
def test_mobile_alt_enter_newline(page, server, playwright):
    # Set up mobile context
    device = playwright.devices["Pixel 5"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**device)
    mobile_page = context.new_page()
    mobile_page.goto(f"{server}/")

    # Start a local session
    expect(mobile_page.get_by_text("Select a Connection").first).to_be_visible(
        timeout=10000
    )
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=10000)
    btns.first.click()

    # Wait for terminal proxy
    expect(mobile_page.locator(".mobile-scroll-proxy")).to_be_visible(timeout=10000)
    mobile_page.locator(".mobile-scroll-proxy").click()

    # Type first line
    mobile_page.keyboard.type("first line")

    # Press Alt+Enter
    mobile_page.keyboard.down("Alt")
    mobile_page.keyboard.press("Enter")
    mobile_page.keyboard.up("Alt")
    mobile_page.wait_for_timeout(500)

    # Type second line
    mobile_page.keyboard.type("second line")
    mobile_page.wait_for_timeout(500)

    # Take screenshot for QA
    mobile_page.screenshot(path="docs/qa-images/alt_enter_newline_proof.png")

    context.close()
    browser.close()
