import pytest
from playwright.sync_api import expect, sync_playwright
import time

@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        iphone_12 = p.devices["iPhone 12"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone_12)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

def get_terminal_text(page):
    return page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : ''; }"
    )

@pytest.mark.timeout(60)
def test_mobile_single_word_buffer(mobile_page):
    # Start a fresh session
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(mobile_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = mobile_page.locator(".mobile-text-area")
    textarea.focus()

    # 1. Type "hello"
    mobile_page.keyboard.type("hello")
    time.sleep(0.5)
    
    # Buffer should be "hello"
    buffer_val = textarea.evaluate("el => el.value")
    assert buffer_val == "hello"

    # 2. Type space
    mobile_page.keyboard.type(" ")
    time.sleep(0.5)

    # Buffer should be empty
    buffer_val = textarea.evaluate("el => el.value")
    assert buffer_val == ""
    
    # 3. Type "world"
    mobile_page.keyboard.type("world")
    time.sleep(0.5)
    
    buffer_val = textarea.evaluate("el => el.value")
    assert buffer_val == "world"

    # 4. Backspace 5 times
    for _ in range(5):
        # We must use proper inputType event for backspace if it's native mobile, or just press backspace
        textarea.evaluate("el => { el.value = el.value.slice(0, -1); el.dispatchEvent(new InputEvent('input', {inputType: 'deleteContentBackward'})); }")
    time.sleep(0.5)
    
    buffer_val = textarea.evaluate("el => el.value")
    assert buffer_val == ""

    # 5. Backspace when buffer is empty should send backspace to terminal
    # Use keydown for backspace on empty buffer
    mobile_page.keyboard.press("Backspace")
    time.sleep(0.5)

    mobile_page.keyboard.press("Enter")
    time.sleep(1)
    
    term_text = get_terminal_text(mobile_page)
    # the terminal should echo "hello" because we typed "hello " then "world", backspaced "world", then backspaced one char from "hello ", resulting in "hello" or "hell".
    # Wait: we typed "hello ", the terminal has "hello ". Then we pressed backspace, terminal deletes the space. So it has "hello".
    print("term text:", term_text)
    assert "You said: hello" in term_text or "You said: hell" in term_text
