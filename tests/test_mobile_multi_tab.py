import pytest
from playwright.sync_api import expect, sync_playwright
import time


@pytest.fixture(scope="function")
def android_page(server):
    with sync_playwright() as p:
        pixel = p.devices["Pixel 5"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**pixel)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


def get_terminal_text(page, tab_index):
    return page.evaluate(f"""
        (() => {{
            const activeTab = tabs[{tab_index}];
            return (activeTab && activeTab.term) ? Array.from({{length: activeTab.term.buffer.active.length}}).map((_, i) => activeTab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : '';
        }})()
    """)


@pytest.mark.timeout(60)
def test_mobile_multi_tab_input(android_page):
    # Start Tab 1
    btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(android_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    # Type in Tab 1
    textarea1 = android_page.locator(".mobile-text-area:visible")
    textarea1.focus()
    textarea1.evaluate(
        "el => { el.value = 'hello'; el.dispatchEvent(new InputEvent('input', {data: 'o'})); }"
    )
    android_page.keyboard.press("Enter")
    time.sleep(1)

    # Verify Tab 1 has text
    text1 = get_terminal_text(android_page, 0)
    assert "hello" in text1

    # Open Tab 2
    android_page.locator("#new-tab-btn").click()
    time.sleep(1)
    btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(android_page.locator(".tab-instance.active .xterm-screen")).to_be_visible(
        timeout=15000
    )
    time.sleep(1)

    # Type in Tab 2
    textarea2 = android_page.locator(".mobile-text-area:visible")
    textarea2.focus()
    textarea2.evaluate(
        "el => { el.value = 'world'; el.dispatchEvent(new InputEvent('input', {data: 'd'})); }"
    )
    android_page.keyboard.press("Enter")
    time.sleep(1)

    # Verify Tab 2 has text but Tab 1 doesn't have 'world'
    text1_after = get_terminal_text(android_page, 0)
    text2 = get_terminal_text(android_page, 1)

    assert "hello" in text1_after
    assert "world" not in text1_after
    assert "world" in text2

    # Switch back to Tab 1
    android_page.evaluate("switchTab(tabs[0].id)")
    time.sleep(1)

    # Type in Tab 1 again
    textarea1_again = android_page.locator(".mobile-text-area:visible")
    textarea1_again.focus()
    textarea1_again.evaluate(
        "el => { el.value = 'again'; el.dispatchEvent(new InputEvent('input', {data: 'n'})); }"
    )
    android_page.keyboard.press("Enter")
    time.sleep(1)

    # Verify Tab 1 gets 'again', Tab 2 doesn't
    text1_final = get_terminal_text(android_page, 0)
    text2_final = get_terminal_text(android_page, 1)

    assert "again" in text1_final
    assert "again" not in text2_final
