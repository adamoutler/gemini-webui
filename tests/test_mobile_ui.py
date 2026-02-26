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
def test_mobile_touch_passthrough(mobile_page):
    """Verify that pointer-events toggle on xterm-screen during touch."""
    # Handle auto-resume: if terminal-container is empty, we need to click "Start New"
    # Otherwise, a session might already be loading.
    
    # Wait for either the terminal or the launcher buttons to be visible
    mobile_page.wait_for_function("""
        () => document.querySelector('.xterm-screen') || 
              document.querySelector('.tab-instance.active button:has-text("Start New")')
    """, timeout=8000)

    if not mobile_page.locator('.xterm-screen').is_visible():
        mobile_page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    
    mobile_page.wait_for_selector('.xterm-screen', timeout=5000)
    
    # Debug: Check viewport size
    viewport_size = mobile_page.viewport_size
    print(f"DEBUG: Viewport size: {viewport_size}")
    
    screen = mobile_page.locator('.xterm-screen')
    
    # 1. Capture initial state
    initial_pe = screen.evaluate("el => getComputedStyle(el).pointerEvents")
    print(f"DEBUG: Initial pointer-events: {initial_pe}")
    
    # 2. Trigger touchstart
    mobile_page.dispatch_event('.terminal-instance', 'touchstart')
    touch_pe = screen.evaluate("el => getComputedStyle(el).pointerEvents")
    print(f"DEBUG: Touch pointer-events: {touch_pe}")
    
    # According to our JS: 
    # viewport.style.pointerEvents = 'all'; (on touchstart)
    # But wait, we are checking screen. Our JS doesn't change screen.style anymore!
    # Our CSS changes screen.style via media query.
    
    # 3. Trigger touchend
    mobile_page.dispatch_event('.terminal-instance', 'touchend')
    # Wait for the setTimeout(50)
    time.sleep(0.1)
    end_pe = screen.evaluate("el => getComputedStyle(el).pointerEvents")
    print(f"DEBUG: End pointer-events: {end_pe}")
    
    # The actual behavior we want to test is that the VIEWPORT toggles
    viewport = mobile_page.locator('.xterm-viewport')
    
    # Verify the terminal is in mobile mode
    expect(mobile_page.locator('.terminal-instance')).to_have_attribute('data-mobile', 'true')
    
    # Initial viewport PE should be 'none' (from our JS init)
    expect(viewport).to_have_css("pointer-events", "none")
    
    # Touchstart viewport PE should be 'all'
    mobile_page.dispatch_event('.terminal-instance', 'touchstart')
    expect(viewport).to_have_css("pointer-events", "all")
    
    # Touchend viewport PE should be 'none' (after timeout)
    mobile_page.dispatch_event('.terminal-instance', 'touchend')
    time.sleep(0.2)
    expect(viewport).to_have_css("pointer-events", "none")

