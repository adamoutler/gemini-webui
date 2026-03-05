import pytest
from playwright.sync_api import sync_playwright

def test_swipe_reload():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 393, 'height': 851},
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 10; Pixel 5) AppleWebKit/537.36"
        )
        page = context.new_page()
        page.goto('http://localhost:5000') # assuming app isn't running, wait I need to start the app first.
