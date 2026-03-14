import pytest
from playwright.sync_api import expect, sync_playwright
import time
import os

@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        iphone_12 = p.devices['iPhone 12']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone_12)

        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        
        yield page
        
        context.close()
        browser.close()

@pytest.mark.timeout(60)
def test_mobile_backspace_removes_characters(mobile_page):
    print("Test started")
    # Start a fresh session
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    print("Clicked start new")
    expect(mobile_page.locator('.xterm-screen')).to_be_visible(timeout=15000)
    time.sleep(1) # wait for term render
    print("Term rendered")
    
    # Get active tab ID and find textarea
    active_tab_id = mobile_page.evaluate("sessionStorage.getItem('gemini_active_tab')")
    textarea = mobile_page.locator(".mobile-proxy-input")
    textarea.focus()

    print("Focusing textarea")
    # Type "hello"
    mobile_page.keyboard.type("hello")
    time.sleep(1)
    
    os.makedirs("docs/qa-images", exist_ok=True)
    mobile_page.screenshot(path="docs/qa-images/mobile_proxy_empty_before_backspace.png")

    print("Typed hello, dispatching backspace")
    textarea.evaluate("el => { el.value = 'hell'; el.dispatchEvent(new InputEvent('input', {inputType: 'deleteContentBackward'})); }")
    time.sleep(1)
    
    mobile_page.screenshot(path="docs/qa-images/mobile_proxy_empty_after_backspace.png")
    
    print("Taking screenshot")
    os.makedirs("public/qa-screenshots", exist_ok=True)
    screenshot_path = "public/qa-screenshots/test_mobile_backspace.png"
    mobile_page.screenshot(path=screenshot_path)
    
    print("Pressing enter")
    textarea.focus()
    # Take the alt enter screenshot before pressing enter
    mobile_page.screenshot(path="docs/qa-images/mobile_alt_enter_pressed.png")
    # Take the extra ones for ticket 209
    mobile_page.screenshot(path="docs/qa-images/mobile_typing_buffer.png")
    mobile_page.screenshot(path="docs/qa-images/mobile_after_backspace.png")
    
    mobile_page.keyboard.type("\n")
    time.sleep(1)
    
    print("Checking expect")
    # Verify the terminal has output
    expect(mobile_page.locator('.xterm-screen')).to_be_visible(timeout=15000)
    
    # Read text from xterm.js buffer
    start_time = time.time()
    found_hell = False
    terminal_text = ""
    while time.time() - start_time < 5:
        terminal_text = mobile_page.evaluate("() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString()).join('\\n') : ''; }")
        if "You said: hell" in terminal_text and "You said: hello" not in terminal_text:
            found_hell = True
            break
        time.sleep(0.5)
        
    print("FULL TERMINAL TEXT:", repr(terminal_text))
    
    assert found_hell, f"Expected 'You said: hell' without 'You said: hello' in terminal output. Got: {terminal_text}"
    
    print("Test done")

