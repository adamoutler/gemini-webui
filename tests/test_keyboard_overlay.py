import pytest
import os
from playwright.sync_api import sync_playwright, expect
import time

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(60000)
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(60)
def test_keyboard_per_word_overlay(page, server):
    page.goto(server)
    
    # Click "Start New" for local connection
    page.wait_for_selector('text="Start New"')
    page.click('text="Start New"')
    
    # Wait for the terminal to be ready
    page.wait_for_selector('.xterm')
    
    # Click to focus
    page.click('.xterm')
    page.wait_for_timeout(1000)
    
    # The overlay textarea
    textarea_selector = '.xterm-helper-textarea'
    
    # Ensure it exists
    page.wait_for_selector(textarea_selector, state="attached")
    
    # Type a word without space
    page.keyboard.type("echo")
    page.wait_for_timeout(500)
    
    # Assert the value is "echo"
    overlay_val = page.locator(textarea_selector).evaluate("el => el.value")
    assert overlay_val == "echo", f"Expected 'echo', got '{overlay_val}'"
    
    import warnings
    screenshot_path = f"/tmp/gemwe-178_{os.environ.get('BUILD_NUMBER', 'local')}.png"
    page.screenshot(path=screenshot_path)
    warnings.warn(f"Empirical evidence: Screenshot saved to {screenshot_path}. Typed 'echo' and found '{overlay_val}' in overlay textarea before space.")
    
    # Type a space
    page.keyboard.press("Space")
    page.wait_for_timeout(500)
    
    # Assert the value is cleared
    overlay_val = page.locator(textarea_selector).evaluate("el => el.value")
    assert overlay_val == "", f"Expected empty string after space, got '{overlay_val}'"
    
    # Type another word
    page.keyboard.type("hello")
    page.wait_for_timeout(500)
    
    overlay_val = page.locator(textarea_selector).evaluate("el => el.value")
    assert overlay_val == "hello", f"Expected 'hello', got '{overlay_val}'"
