import pytest
import time
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.prone_to_timeout
@pytest.mark.timeout(20)
def test_ctrl_enter_aliases_to_alt_enter(page):
    """Verify that pressing Ctrl+Enter in the terminal sends the Alt+Enter sequence."""
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=5000)

    # Start a fresh local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()
    
    # Wait for terminal to appear
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)

    # Wait for connection to establish and welcome message
    page.wait_for_function("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 5; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString() + "\\n";
            }
            return out.includes("Welcome to Fake Gemini");
        }
        return false;
    }""", timeout=10000)

    # Focus the terminal
    page.locator('.xterm-helper-textarea').first.focus()

    # Type a message
    page.locator('.xterm-helper-textarea').first.fill("secret_test_string")
    
    # Simulate pressing Control+Enter
    page.locator('.xterm-helper-textarea').first.press("Control+Enter")
    
    # Wait for the backend response
    time.sleep(2)
    
    content = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 20; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString() + "\\n";
            }
            return out;
        }
        return "";
    }""")

    print(f"TERMINAL CONTENT:\n{content}")
    assert "ALT_ENTER_RECEIVED" in content, f"Did not find ALT_ENTER_RECEIVED in terminal output: {content}"
