import pytest
from playwright.sync_api import expect, sync_playwright
import time


@pytest.fixture(scope="function")
def mobile_page(server, playwright):
    p = playwright
    if True:
        iphone_12 = p.devices["iPhone 12"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone_12)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


def get_terminal_text(page):
    return page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : ''; }"
    )


@pytest.mark.timeout(60)
def test_mobile_paste(mobile_page):
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(mobile_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = mobile_page.locator(".mobile-text-area")
    textarea.focus()

    # Simulate paste
    textarea.evaluate(
        "el => { el.value = 'hello pasted text'; el.dispatchEvent(new InputEvent('input', {inputType: 'insertFromPaste'})); }"
    )
    time.sleep(0.5)

    # Send enter so the mock_gemini_cli echoes it
    mobile_page.keyboard.press("Enter")
    time.sleep(1)

    term_text = get_terminal_text(mobile_page)
    # The terminal should echo "hello pasted text"
    assert "You said: hello pasted text" in term_text
