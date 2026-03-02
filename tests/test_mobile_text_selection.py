import pytest
import time
from playwright.sync_api import sync_playwright, expect

# Individual test execution MUST NOT exceed 20 seconds.
MAX_TEST_TIME = 20.0

@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        # Emulate Pixel 5
        device = p.devices['Pixel 5']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(20)
def test_mobile_text_selection_overlay(mobile_page):
    """Verify that the mobile text selection overlay is populated on touchstart."""
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # Wait for the prompt to appear
    mobile_page.wait_for_timeout(2000)
    
    # Ensure overlay exists
    overlay = mobile_page.locator(".mobile-selection-overlay")
    expect(overlay.first).to_be_attached(timeout=5000)
    
    # Initially it might be empty or not empty depending on if touch happened. 
    # Let's trigger a touchstart on the proxy
    proxy = mobile_page.locator(".mobile-scroll-proxy").first
    
    # Trigger a touchstart event to populate the overlay by tapping on it
    # We use page.touchscreen.tap to simulate a real touch
    proxy_box = proxy.bounding_box()
    mobile_page.touchscreen.tap(proxy_box["x"] + 10, proxy_box["y"] + 10)
    
    # Check if the overlay now has text content from the terminal
    text_content = overlay.first.text_content()
    assert text_content is not None
    # Assuming there's some text like "gemini" or bash prompt in the terminal
    # The overlay should contain something non-empty
    assert len(text_content.strip()) > 0
