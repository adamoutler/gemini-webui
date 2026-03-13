# Resolves Tickets 172, 171, 170, 169, 168, 167, 166, 143, 142, 141
import pytest
import time
from playwright.sync_api import sync_playwright, expect

MAX_TEST_TIME = 120.0

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(120000)
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.prone_to_timeout
@pytest.mark.timeout(120)
def test_ui_share_workflow(page, server):
    """Verify that a user can share a session and generate a link."""
    print("Starting test_ui_share_workflow")
    # Start a fresh local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    print("Waiting for Start New button")
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    print("Waiting for connection info")
    # Wait for terminal to appear
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=15000)
    expect(page.locator('#share-session-btn')).to_be_visible(timeout=15000)
    
    print("Waiting for xterm-screen")
    # Wait for terminal xterm-screen
    expect(page.locator('.xterm-screen')).to_be_visible(timeout=15000)
    
    time.sleep(1) # wait a little bit for term render

    print("Clicking share session btn")
    # Click Share Session
    page.locator('#share-session-btn').click()

    print("Waiting for share modal")
    # Verify modal appears
    expect(page.locator('#share-modal')).to_be_visible(timeout=15000)
    time.sleep(1)
    expect(page.locator('#share-modal')).to_contain_text("This will generate a publicly accessible link.", timeout=15000)

    print("Waiting for api request")
    # Click confirm and wait for API request
    with page.expect_request("**/api/shares/create") as req_info:
        page.locator('#confirm-share-btn').click()
    
    print("Validating request")
    req = req_info.value
    assert req.method == "POST"
    
    post_data = req.post_data_json
    assert "html_content" in post_data
    assert post_data.get("theme") == "full"
    
    print("Waiting for share result")
    # Wait for result to be visible
    expect(page.locator('#share-result')).to_be_visible(timeout=15000)
    
    print("Validating link input")
    # Verify the generated link exists
    link_input = page.locator('#share-link-input')
    expect(link_input).to_be_visible()
    
    val = link_input.input_value()
    assert "/s/" in val

    print("Navigating to link")
    # Navigate to the generated link

    new_page = page.context.new_page()
    new_page.set_default_timeout(120000)
    new_page.goto(val, timeout=15000)
    
    print("Validating new page")
    # Verify structural classes and layout
    expect(new_page.locator('body')).to_have_class('theme-full')
    expect(new_page.locator('.terminal-wrapper')).to_be_visible()
    
    # Verify the inner terminal div does not override the background
    inner_bg = new_page.evaluate('''() => {
        const el = document.querySelector(".terminal-wrapper").firstElementChild;
        return el ? window.getComputedStyle(el).backgroundColor : null;
    }''')
    
    if inner_bg is not None:
        assert inner_bg in ['rgba(0, 0, 0, 0)', 'rgb(255, 255, 255)', 'transparent'], f"Expected inner div to not have hardcoded black background, got {inner_bg}"
    
    new_page.close()
    print("Test finished")
