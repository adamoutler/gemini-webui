import pytest
from playwright.sync_api import expect, sync_playwright
import time


@pytest.fixture(scope="function")
def android_page(server, playwright):
    p = playwright
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
def test_mobile_double_space_backspace(android_page, playwright):
    btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(android_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = android_page.locator(".mobile-text-area")
    textarea.focus()

    # Type "hello"
    textarea.evaluate(
        "el => { el.value = 'hello'; el.dispatchEvent(new InputEvent('input', {data: 'o', inputType: 'insertText'})); }"
    )
    time.sleep(0.5)

    # Type 1st space
    textarea.evaluate(
        "el => { el.value += ' '; el.dispatchEvent(new InputEvent('input', {data: ' ', inputType: 'insertText'})); }"
    )
    time.sleep(0.5)

    # Type 2nd space (triggers auto-period -> ".\x20" sent to terminal, proxy input cleared)
    textarea.evaluate(
        "el => { el.value += ' '; el.dispatchEvent(new InputEvent('input', {data: ' ', inputType: 'insertText'})); }"
    )
    time.sleep(0.5)

    text_after_double_space = get_terminal_text(android_page)
    # The terminal should have "hello. " (with trailing space)
    assert "hello." in text_after_double_space

    # Press Backspace 1 (removes the space)
    textarea.press("Backspace")
    time.sleep(0.5)

    # Press Backspace 2 (removes the period)
    textarea.press("Backspace")
    time.sleep(0.5)

    # We should just have "hello" now.
    text_after_backspace = get_terminal_text(android_page)
    assert "hello." not in text_after_backspace

    # Now type multiple spaces. They should NOT trigger another period.
    # 1st space
    textarea.evaluate(
        "el => { el.value += ' '; el.dispatchEvent(new InputEvent('input', {data: ' ', inputType: 'insertText'})); }"
    )
    time.sleep(0.5)

    # 2nd space
    textarea.evaluate(
        "el => { el.value += ' '; el.dispatchEvent(new InputEvent('input', {data: ' ', inputType: 'insertText'})); }"
    )
    time.sleep(0.5)

    # Type "world"
    textarea.evaluate(
        "el => { el.value += 'world'; el.dispatchEvent(new InputEvent('input', {data: 'd', inputType: 'insertText'})); }"
    )
    time.sleep(0.5)

    android_page.keyboard.press("Enter")
    time.sleep(1)

    android_page.screenshot(
        path="public/qa-screenshots/proof_mobile_backspace_double_space.png"
    )
    final_text = get_terminal_text(android_page)
    print("FINAL TERMINAL TEXT:", repr(final_text))
    # Check that there are no periods added automatically after the backspace
    assert "hello  world" in final_text
    assert "hello." not in final_text
