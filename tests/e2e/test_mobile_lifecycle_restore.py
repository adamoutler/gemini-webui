import os
import pytest
from playwright.sync_api import expect


@pytest.fixture
def mobile_context(playwright):
    iphone_13 = playwright.devices["iPhone 13"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**iphone_13)
    yield context
    browser.close()


def test_mobile_lifecycle_restore(server, mobile_context):
    page = mobile_context.new_page()
    page.goto(server)

    # Wait for UI to load
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)

    # Emulate mobile explicitly since we are testing mobile behavior
    page.evaluate("document.documentElement.classList.add('is-mobile')")

    # Start session
    page.locator('button:has-text("Start New")').first.click()

    # Wait for terminal
    page.wait_for_selector(".xterm-rows", timeout=15000)
    page.wait_for_timeout(1000)

    # Focus terminal
    page.locator(".mobile-scroll-proxy").first.click()

    # Fast output to fill the buffer (256KB)
    page.evaluate("""() => {
        for (let i = 0; i < 500; i++) {
            let pattern = 'X'.repeat(400) + ' Line ' + i.toString().padStart(3, '0') + '\\n';
            tabs.find(t => t.id === activeTabId).socket.emit('pty-input', { input: pattern });
        }
    }""")

    # Wait for it to finish and settle
    page.wait_for_timeout(5000)

    # Verify the last lines are visible
    expect(page.locator(".xterm-rows")).to_contain_text("Line 499")

    # Screenshot 1
    os.makedirs("public/qa-screenshots", exist_ok=True)
    page.screenshot(path="public/qa-screenshots/mobile-buffer-01-before-background.png")

    # Trigger background
    page.evaluate("""
        Object.defineProperty(document, 'hidden', {configurable: true, get: function() { return true; }});
        Object.defineProperty(document, 'visibilityState', {configurable: true, get: function() { return 'hidden'; }});
        document.dispatchEvent(new Event('visibilitychange'));
    """)
    page.wait_for_timeout(1000)

    # Trigger foreground
    page.evaluate("""
        Object.defineProperty(document, 'hidden', {configurable: true, get: function() { return false; }});
        Object.defineProperty(document, 'visibilityState', {configurable: true, get: function() { return 'visible'; }});
        document.dispatchEvent(new Event('visibilitychange'));
    """)
    page.wait_for_timeout(1000)

    # Verify text is STILL there
    expect(page.locator(".xterm-rows")).to_contain_text("Line 499")

    # Screenshot 2
    page.screenshot(path="public/qa-screenshots/mobile-buffer-02-after-foreground.png")
