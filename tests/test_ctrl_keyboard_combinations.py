import pytest
import time
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="module")
def browser_context():
    with sync_playwright() as playwright:
        device = playwright.devices['Desktop Chrome']
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        context.close()
        browser.close()

@pytest.fixture(scope="function")
def page(server, browser_context):
    page = browser_context.new_page()
    page.goto(server, timeout=15000)
    page.locator('#new-tab-btn').click()
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)
    yield page
    page.close()

def test_physical_keyboard_combinations(page):
    # Override emitPtyInput to catch what is being sent
    page.evaluate("""() => {
        window.sentInputs = [];
        const originalEmit = emitPtyInput;
        window.emitPtyInput = function(tab, data) {
            window.sentInputs.push(data);
            originalEmit(tab, data);
        };
    }""")
    
    # Wait for the focus to settle on textarea
    active_tab_id = page.evaluate("sessionStorage.getItem('gemini_active_tab')")
    textarea = page.locator(f"#terminal-input-{active_tab_id}")
    
    # Click to ensure focus
    textarea.click()
    
    # Press Ctrl+C
    page.keyboard.press("Control+c")
    
    # Press Ctrl+D
    page.keyboard.press("Control+d")
    
    # Press Ctrl+L
    page.keyboard.press("Control+l")
    
    # Wait for processing
    page.wait_for_timeout(500)
    
    # Check what was sent
    sent = page.evaluate("window.sentInputs")
    print("Sent inputs:", sent)
    
    # Ctrl+C is \x03, Ctrl+D is \x04, Ctrl+L is \x0c
    assert "\x03" in sent, "Ctrl+C was not sent"
    assert "\x04" in sent, "Ctrl+D was not sent"
    assert "\x0c" in sent, "Ctrl+L was not sent"
