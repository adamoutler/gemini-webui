import pytest
from playwright.sync_api import expect, sync_playwright
import time


@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        iphone_12 = p.devices["iPhone 12"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone_12)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


@pytest.mark.timeout(60)
def test_mobile_keyboard_flash(mobile_page):
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(mobile_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = mobile_page.locator(".mobile-text-area")

    # Track blur events on proxyInput
    mobile_page.evaluate("""() => {
        window.blurCount = 0;
        const proxy = document.querySelector('.mobile-text-area');
        proxy.addEventListener('blur', () => window.blurCount++);
    }""")

    # Tap terminal once
    mobile_page.locator(".xterm-screen").tap()
    time.sleep(0.5)

    # Should be focused
    is_focused = mobile_page.evaluate(
        "document.activeElement === document.querySelector('.mobile-text-area')"
    )
    assert is_focused, "Proxy input should be focused after tap"

    # Reset blur count
    mobile_page.evaluate("window.blurCount = 0")

    # Tap terminal again
    mobile_page.locator(".xterm-screen").tap()
    time.sleep(0.5)

    blur_count = mobile_page.evaluate("window.blurCount")

    # If blur_count > 0, it means the proxyInput lost focus and regained it (flashing the keyboard)
    assert blur_count == 0, f"Keyboard flashed! Blur count was {blur_count}"
