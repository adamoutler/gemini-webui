import pytest
import time
from playwright.sync_api import sync_playwright, expect

# Individual test execution MUST NOT exceed 10 seconds.
MAX_TEST_TIME = 10.0

@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        # Emulate Pixel 5
        device = p.devices['Pixel 5']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=10000)
        page.wait_for_selector("#tab-bar", timeout=5000)
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(10)
def test_mobile_absolute_proxy(mobile_page):
    """Verify that Absolute Proxy scroller is configured correctly."""
    # Wait for either the terminal or any button in the active launcher tab
    mobile_page.wait_for_function("""
        () => document.querySelector('.xterm-screen') || 
              Array.from(document.querySelectorAll('.tab-instance.active button')).find(b => b.innerText.includes('Start New'))
    """, timeout=8000)

    if not mobile_page.locator('.xterm-screen').is_visible():
        mobile_page.locator('.tab-instance.active button').filter(has_text="Start New").first.click()
    
    mobile_page.wait_for_selector('.mobile-scroll-proxy', timeout=5000)
    
    proxy = mobile_page.locator('.mobile-scroll-proxy')
    
    # 1. Proxy should be on top and capture gestures
    expect(proxy).to_be_visible()
    pe = proxy.evaluate("el => getComputedStyle(el).pointerEvents")
    assert pe in ["all", "auto"], f"Unexpected pointer-events: {pe}"
    expect(proxy).to_have_css("z-index", "100")
    
    # 2. Check for the large scrollable area
    content = proxy.locator('.mobile-scroll-content')
    expect(content).to_have_css("height", "100000px")
    
    # 3. Simulate Tap Passthrough
    mobile_page.mouse.move(100, 100)
    mobile_page.mouse.down()
    mobile_page.mouse.up()
    
    # After a tap, it should briefly be none then return to all
    # We wait for the timeout in our JS
    time.sleep(0.5)
    pe_after = proxy.evaluate("el => getComputedStyle(el).pointerEvents")
    assert pe_after in ["all", "auto"], f"Unexpected pointer-events after tap: {pe_after}"

