import pytest
import time
from playwright.sync_api import sync_playwright, expect
from PIL import Image
import io

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(30)
def test_full_color_logo(page, server):
    # Start a fresh local session which prints the Gemini logo
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()

    expect(page.locator('.xterm-screen')).to_be_visible(timeout=5000)
    time.sleep(2) # wait for term render and logo printing
    
    # Share session
    page.locator('#share-session-btn').click()
    expect(page.locator('#share-modal')).to_be_visible(timeout=5000)
    
    # Select full color theme
    page.locator('#share-theme-select').select_option('full')
    page.locator('#confirm-share-btn').click()
    
    expect(page.locator('#share-result')).to_be_visible(timeout=5000)
    link_input = page.locator('#share-link-input')
    expect(link_input).to_be_visible()
    
    val = link_input.input_value()
    
    # Navigate to the generated link
    new_page = page.context.new_page()
    new_page.goto(val, timeout=15000)
    
    expect(new_page.locator('.terminal-wrapper')).to_be_visible(timeout=5000)
    time.sleep(1)
    
    screenshot_path = "public/qa-screenshots/test_share_full_logo.png"
    import os
    os.makedirs("public/qa-screenshots", exist_ok=True)
    new_page.screenshot(path=screenshot_path)
    
    # Analyze elements with inline color styles
    # We expect multiple different colors because the Gemini logo is colorful
    colored_spans = new_page.locator('span[style*="color"]')
    count = colored_spans.count()
    assert count > 0, "No explicitly colored spans found. The Full Color theme is not preserving colors."
    
    colors_found = set()
    for i in range(count):
        style = colored_spans.nth(i).get_attribute("style")
        if style and "color:" in style:
            # Extract the color value
            import re
            m = re.search(r"color:\s*([^;]+)", style)
            if m:
                colors_found.add(m.group(1).strip())
                
    print(f"Colors found: {colors_found}")
    # The logo uses at least 3 distinct colors usually
    assert len(colors_found) >= 2, f"Expected multiple colors for the logo, found: {colors_found}"
    
    new_page.close()
