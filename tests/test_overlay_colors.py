import pytest
import warnings
import os
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        yield page
        context.close()
        browser.close()

def test_overlay_color(page):
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    page.wait_for_selector(".xterm-helper-textarea", state="attached", timeout=15000)
    
    # Get computed styles
    style = page.evaluate('''() => {
        const el = document.querySelector(".xterm-helper-textarea");
        const style = window.getComputedStyle(el);
        return { bg: style.backgroundColor, fg: style.color };
    }''')
    print("Computed Styles of xterm-helper-textarea:", style)

    term_style = page.evaluate('''() => {
        const el = document.querySelector(".terminal");
        if (!el) return null;
        const style = window.getComputedStyle(el);
        return { bg: style.backgroundColor, fg: style.color };
    }''')
    print("Computed Styles of terminal:", term_style)
    
    assert style['bg'] in ['rgba(0, 0, 0, 0)', 'transparent'], f"Expected transparent background, got {style['bg']}"
    assert style['fg'] == term_style['fg'], f"Expected '{term_style['fg']}', got {style['fg']}"

    screenshot_path = f"/tmp/gemwe-179_{os.environ.get('BUILD_NUMBER', 'local')}.png"
    page.screenshot(path=screenshot_path)
    print(f"Empirical evidence: Screenshot saved to {screenshot_path}. Computed overlay styles: background={style['bg']}, foreground={style['fg']}. Computed terminal styles: background={term_style['bg']}, foreground={term_style['fg']}.")
