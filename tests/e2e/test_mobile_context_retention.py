import pytest
from playwright.sync_api import expect
import time


@pytest.fixture(scope="function")
def mobile_page(server, playwright):
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


@pytest.mark.timeout(60)
def test_mobile_context_retention(mobile_page, playwright):
    print("Test started")
    # Start a fresh session
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(mobile_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)  # wait for term render

    # Focus textarea
    textarea = mobile_page.locator(".mobile-text-area")
    textarea.focus()

    # Type command to generate output
    mobile_page.keyboard.type("echo 'TEST_CONTEXT_RETENTION_12345'\n")
    time.sleep(1)

    # Read text from xterm.js buffer
    start_time = time.time()
    found_text = False
    terminal_text = ""
    while time.time() - start_time < 5:
        terminal_text = mobile_page.evaluate(
            "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString()).join('\\n') : ''; }"
        )
        if "TEST_CONTEXT_RETENTION_12345" in terminal_text:
            found_text = True
            break
        time.sleep(0.5)

    assert found_text, f"Expected 'TEST_CONTEXT_RETENTION_12345' in terminal output. Got: {terminal_text}"

    # Simulate backgrounding (disconnect)
    mobile_page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); if (tab) tab.socket.disconnect(); }"
    )
    time.sleep(2)

    # Simulate foregrounding (reconnect)
    mobile_page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); if (tab) tab.socket.connect(); }"
    )
    time.sleep(3)

    # Verify the output is fully restored via chunked transmission
    start_time = time.time()
    found_restored_text = False
    restored_terminal_text = ""
    while time.time() - start_time < 5:
        restored_terminal_text = mobile_page.evaluate(
            "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString()).join('\\n') : ''; }"
        )
        # Should contain the previously typed echo output
        if "TEST_CONTEXT_RETENTION_12345" in restored_terminal_text:
            found_restored_text = True
            break
        time.sleep(0.5)

    assert found_restored_text, f"Expected 'TEST_CONTEXT_RETENTION_12345' after reconnect. Got: {restored_terminal_text}"
    print("Test passed")
