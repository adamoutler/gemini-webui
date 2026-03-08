import pytest
from playwright.sync_api import sync_playwright, expect
import time

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

def test_ctrl_sticky_modifier(mobile_page):
    ctrl_btn = mobile_page.locator("#ctrl-toggle")
    
    # Listen to console for debug
    messages = []
    mobile_page.on("console", lambda msg: messages.append(msg.text))
    
    # Override emitPtyInput to catch what is being sent
    mobile_page.evaluate("""() => {
        window.sentInputs = [];
        const originalEmit = emitPtyInput;
        window.emitPtyInput = function(tab, data) {
            window.sentInputs.push(data);
            originalEmit(tab, data);
        };
    }""")
    
    # Tap Ctrl
    ctrl_btn.tap()
    expect(ctrl_btn).to_have_class("control-btn active")
    
    # Wait for the focus to settle on textarea
    active_tab_id = mobile_page.evaluate("sessionStorage.getItem('gemini_active_tab')")
    textarea = mobile_page.locator(f"#terminal-input-{active_tab_id}")
    
    # Fill the textarea as if user is typing 'c'
    textarea.fill('c')
    
    # Wait for processing
    mobile_page.wait_for_timeout(500)
    
    # Check if Ctrl was cleared
    expect(ctrl_btn).not_to_have_class("control-btn active")
    
    # Check what was sent
    sent = mobile_page.evaluate("window.sentInputs")
    print("Sent inputs:", sent)
    
    # We expect \x03 because ctrl + c
    assert "\x03" in sent
