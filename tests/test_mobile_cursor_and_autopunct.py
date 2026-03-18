import pytest
from playwright.sync_api import expect, sync_playwright
import time
from tests.playwright_mobile_utils import (
    simulateAutocorrect,
    simulateSpacebarTrackpad,
    simulateAutoPunctuation,
)


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


def get_terminal_text(page):
    return page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : ''; }"
    )


@pytest.mark.timeout(60)
def test_mobile_autopunctuation(android_page):
    btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(android_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = android_page.locator(".mobile-text-area")
    textarea.focus()

    # Type "hello "
    textarea.evaluate(
        "el => { el.value = 'hello '; el.dispatchEvent(new InputEvent('input', {data: ' '})); }"
    )
    time.sleep(0.5)

    # OS auto-punctuates (sends ". ")
    simulateAutoPunctuation(android_page, ".")
    time.sleep(0.5)

    android_page.keyboard.press("Enter")
    time.sleep(1)

    text = get_terminal_text(android_page)
    # The terminal output should be "hello." because the space was replaced,
    # and the trailing space is stripped by get_terminal_text or fake gemini
    assert "hello." in text


@pytest.mark.timeout(60)
def test_mobile_cursor_placement(android_page):
    btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(android_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = android_page.locator(".mobile-text-area")
    textarea.focus()

    # Type "abc"
    textarea.evaluate(
        "el => { el.value = 'abc'; el.dispatchEvent(new InputEvent('input', {data: 'c'})); el.selectionStart = 3; el.selectionEnd = 3; }"
    )
    time.sleep(0.5)

    # Move cursor left by 2 (trackpad)
    simulateSpacebarTrackpad(android_page, -2)
    time.sleep(0.5)

    # Type "X"
    textarea.evaluate(
        "el => { el.value = 'aXbc'; el.dispatchEvent(new InputEvent('input', {data: 'X'})); }"
    )
    time.sleep(0.5)

    android_page.keyboard.press("Enter")
    time.sleep(1)

    text = get_terminal_text(android_page)
    # The terminal output should reflect "aXbc"
    assert "aXbc" in text
