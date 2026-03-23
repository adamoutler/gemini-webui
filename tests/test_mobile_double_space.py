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


def get_terminal_text(page):
    return page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : ''; }"
    )


@pytest.mark.timeout(60)
def test_mobile_double_space(android_page):
    android_page.on("console", lambda msg: print(f"BROWSER_CONSOLE: {msg.text}"))
    btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(android_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = android_page.locator(".mobile-text-area")
    textarea.focus()

    # Define a helper to type text character by character exactly like a mobile keyboard does
    android_page.evaluate("""() => {
        window.simulateMobileTyping = (text) => {
            const el = document.querySelector('.mobile-text-area');
            for (let i = 0; i < text.length; i++) {
                const char = text[i];
                el.dispatchEvent(new KeyboardEvent('keydown', {key: char}));
                el.value += char;
                el.dispatchEvent(new InputEvent('input', {data: char, inputType: 'insertText'}));
            }
        };
    }""")

    # Type "hello"
    android_page.evaluate("window.simulateMobileTyping('hello')")
    time.sleep(0.5)

    # Type space
    android_page.evaluate("window.simulateMobileTyping(' ')")
    time.sleep(0.1)

    # User types space again (double tap)
    android_page.evaluate("window.simulateMobileTyping(' ')")
    time.sleep(0.5)

    # Type "world"
    android_page.evaluate("window.simulateMobileTyping('world')")
    time.sleep(0.5)

    android_page.keyboard.press("Enter")
    time.sleep(1)

    text = get_terminal_text(android_page)
    print("TERMINAL TEXT:", repr(text))
    assert "hello. world" in text
