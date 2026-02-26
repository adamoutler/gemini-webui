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
def test_mobile_physics_momentum(mobile_page):
    """Verify that Physics-First momentum rules are applied on mobile."""
    # Wait for either the terminal or any button in the active launcher tab
    mobile_page.wait_for_function("""
        () => document.querySelector('.xterm-screen') || 
              Array.from(document.querySelectorAll('.tab-instance.active button')).find(b => b.innerText.includes('Start New'))
    """, timeout=8000)

    if not mobile_page.locator('.xterm-screen').is_visible():
        mobile_page.locator('.tab-instance.active button').filter(has_text="Start New").first.click()
    
    mobile_page.wait_for_selector('.xterm-viewport', timeout=5000)
    
    viewport = mobile_page.locator('.xterm-viewport')
    
    # 1. Viewport should be on top (high z-index) and have pointer-events: all
    expect(viewport).to_be_visible()
    expect(viewport).to_have_css("pointer-events", "all")
    expect(viewport).to_have_css("z-index", "10")
    
    # 2. Verify it's full width (allowing for parent container padding)
    is_full_width = viewport.evaluate("""el => {
        const parentWidth = el.parentElement.clientWidth;
        return Math.abs(el.clientWidth - parentWidth) <= 2;
    }""")
    assert is_full_width, "Viewport should be full-width to capture all swipes"
    
    # 3. Quick Tap should NOT permanently disable viewport
    # Use mouse API which Playwright correctly translates to touch in mobile context
    viewport_box = viewport.bounding_box()
    center_x = viewport_box['x'] + viewport_box['width'] / 2
    center_y = viewport_box['y'] + viewport_box['height'] / 2
    
    mobile_page.mouse.move(center_x, center_y)
    mobile_page.mouse.down()
    mobile_page.mouse.up()
    
    # Viewport should still have pointer-events: all after tap logic
    expect(viewport).to_have_css("pointer-events", "all")
