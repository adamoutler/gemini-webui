import pytest
import time
from playwright.sync_api import sync_playwright, expect

MAX_TEST_TIME = 20.0

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.prone_to_timeout
@pytest.mark.timeout(20)
def test_ui_share_workflow(page, server):
    """Verify that a user can share a session and generate a link."""
    # Start a fresh local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()

    # Wait for terminal to appear
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)
    expect(page.locator('#share-session-btn')).to_be_visible(timeout=5000)
    
    # Wait for terminal xterm-screen
    expect(page.locator('.xterm-screen')).to_be_visible(timeout=5000)
    
    time.sleep(1) # wait a little bit for term render

    # Click Share Session
    page.locator('#share-session-btn').click()

    # Verify modal appears
    expect(page.locator('#share-modal')).to_be_visible(timeout=5000)
    expect(page.locator('#share-modal')).to_contain_text("This will generate a publicly accessible link.", timeout=5000)

    # Select the Light theme
    page.locator('#share-theme-select').select_option('light')

    # Click confirm and wait for API request
    with page.expect_request("**/api/shares/create") as req_info:
        page.locator('#confirm-share-btn').click()
    
    req = req_info.value
    assert req.method == "POST"
    
    post_data = req.post_data_json
    assert "html_content" in post_data
    assert post_data.get("theme") == "light"
    
    # Wait for result to be visible
    expect(page.locator('#share-result')).to_be_visible(timeout=5000)
    
    # Verify the generated link exists
    link_input = page.locator('#share-link-input')
    expect(link_input).to_be_visible()
    
    val = link_input.input_value()
    assert "/s/" in val

    # Navigate to the generated link
    new_page = page.context.new_page()
    new_page.goto(val, timeout=15000)
    
    # Verify structural classes and layout
    expect(new_page.locator('body')).to_have_class('theme-light')
    expect(new_page.locator('.terminal-wrapper')).to_be_visible()
    
    # Verify background color of body based on theme-light css
    body_bg_color = new_page.evaluate('window.getComputedStyle(document.body).backgroundColor')
    assert body_bg_color == 'rgb(255, 255, 255)', f"Expected white background for light theme, got {body_bg_color}"
    
    new_page.close()
