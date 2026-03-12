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
@pytest.mark.timeout(60)
def test_ctrl_enter_aliases_to_alt_enter(page):
    """Verify that pressing Ctrl+Enter in the terminal sends the Alt+Enter sequence."""
    print("STEP 1: Checking for Select a Connection")
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=5000)

    # Start a fresh local session
    print("STEP 2: Clicking Start New")
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()
    
    # Wait for terminal to appear
    print("STEP 3: Waiting for connection info")
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)

    # Wait for connection to establish and welcome message
    print("STEP 4: Waiting for Welcome to Fake Gemini")
    page.wait_for_function("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 5; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString() + "\\n";
            }
            console.log("DEBUG TERMINAL BUFFER:", out);
            return out.includes("Welcome") && out.includes("Fake") && out.includes("Gemini");
        }
        return false;
    }""", timeout=10000)

    # Focus the terminal
    page.locator('.xterm-helper-textarea').first.focus()

    # Type a message
    page.keyboard.type("secret_test_string")
    
    # Simulate pressing Control+Enter
    page.keyboard.press("Control+Enter")
    
    # Wait for the backend response
    # Instead of sleep, wait for function
    page.wait_for_function("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 20; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString() + "\\n";
            }
            return out.includes("ALT_ENTER_RECEIVED");
        }
        return false;
    }""", timeout=10000)
    
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
