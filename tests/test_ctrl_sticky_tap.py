import pytest
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="module")
def browser_context():
    with sync_playwright() as playwright:
        device = playwright.devices['Pixel 5']
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(**device)
        yield context
        context.close()
        browser.close()

@pytest.fixture(scope="function")
def mobile_page(server, browser_context):
    page = browser_context.new_page()
    page.goto(server, timeout=15000)
    page.locator('#new-tab-btn').click()
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)
    expect(page.locator('#mobile-controls')).to_be_visible(timeout=5000)
    yield page
    page.close()

def test_ctrl_sticky_tap(mobile_page):
    ctrl_btn = mobile_page.locator("#ctrl-toggle")
    
    # Use TAP instead of click
    ctrl_btn.tap() 
    
    # It should be active
    expect(ctrl_btn).to_have_class("control-btn active")

    active_tab_id = mobile_page.evaluate("sessionStorage.getItem('gemini_active_tab')")
    textarea = mobile_page.locator(f"#terminal-input-{active_tab_id}")
    
    # Wait to ensure no immediate toggle off happens due to click
    mobile_page.wait_for_timeout(500)
    
    # Check again
    expect(ctrl_btn).to_have_class("control-btn active")
