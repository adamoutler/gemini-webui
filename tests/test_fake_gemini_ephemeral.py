import pytest
import time
import warnings
import os
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        # Connect to host-based Chromium via CDP
        try:
            browser = p.chromium.connect_over_cdp("http://172.20.0.1:9223")
        except Exception as e:
            print(f"Failed to connect to CDP: {e}. Falling back to local launch.")
            browser = p.chromium.launch(headless=True)
        
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        yield page
        context.close()
        browser.close()

def test_fake_gemini_ephemeral(page, server):
    # 1. Navigate to /test-launcher
    page.goto(f"{server}/test-launcher", timeout=15000)
    expect(page.locator("h1:has-text('TEST LAUNCHER')")).to_be_visible()
    
    # Take screenshot of launcher page
    page.screenshot(path="/tmp/launcher_page_220_ephemeral.png")
    print("Saved screenshot to /tmp/launcher_page_220_ephemeral.png")

    # 2. Fill scenario input with ansi_stress_test
    page.locator("input[name='scenario']").fill("ansi_stress_test")
    
    # 3. Click "Launch Fake Session"
    page.locator("button:has-text('Launch Fake Session')").click()
    
    # 4. Assert that the URL now contains mode=fake and a session_id
    page.wait_for_url(lambda url: "mode=fake" in url and "session_id=" in url, timeout=15000)
    url = page.url
    assert "mode=fake" in url
    assert "session_id=" in url
    
    # 5. Assert that the terminal contains "Welcome to Fake Gemini"
    page.wait_for_selector(".terminal-instance", state="attached", timeout=15000)
    page.wait_for_selector(".xterm-helper-textarea", state="attached", timeout=10000)
    
    # Give it a moment to output
    page.wait_for_timeout(3000)
    
    def get_terminal_content():
        return page.evaluate("() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString()).join('\\n') : ''; }")

    rows = get_terminal_content()
    assert "[Fake Gemini v2.0 - High Fidelity Mode]" in rows
    assert f"Scenario: ansi_stress_test" in rows
    assert "Ready for input" in rows
    
    # 6. Assert that document.body has the theme-fake-session class
    has_class = page.evaluate("document.body.classList.contains('theme-fake-session')")
    assert has_class, "document.body should have 'theme-fake-session' class"
    
    # Take screenshot of active fake session terminal
    page.screenshot(path="/tmp/active_fake_session_220_ephemeral.png")
    print("Saved screenshot to /tmp/active_fake_session_220_ephemeral.png")

    # 7. Trigger a page reload and assert that the friction-modal is visible
    # Note: reload might trigger beforeunload dialog if playwright doesn't auto-dismiss it.
    # But we want to see the modal, which happens on beforeunload.
    
    # We can handle the dialog to stay on the page to see the modal
    page.on("dialog", lambda dialog: dialog.dismiss()) 
    
    # Trigger reload (this will trigger beforeunload)
    # We use evaluate to trigger it and stay on page via dialog dismissal
    page.evaluate("window.location.reload()")
    
    # Assert friction-modal is visible
    expect(page.locator("#friction-modal")).to_be_visible(timeout=10000)
    
    # Take screenshot of friction modal
    page.screenshot(path="/tmp/friction_modal_after_reload_220_ephemeral.png")
    print("Saved screenshot to /tmp/friction_modal_after_reload_220_ephemeral.png")

    # 8. Check backend rejection logic
    # Try to open a second tab with the same session_id
    session_id = url.split("session_id=")[1].split("&")[0]
    second_tab_url = f"{server}/?session_id={session_id}&mode=fake"
    
    with page.context.new_page() as second_page:
        second_page.goto(second_tab_url, timeout=15000)
        second_page.wait_for_selector(".terminal-instance", state="attached", timeout=15000)
        second_page.wait_for_timeout(3000)
        
        second_rows = second_page.evaluate("() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString()).join('\\n') : ''; }")
        print("Second Tab Terminal Content:")
        print(second_rows)
        
        # Verify it gets an error message
        assert "This ephemeral session is already active in another window" in second_rows or \
               "This ephemeral session has already been used" in second_rows or \
               "Invalid or expired ephemeral session" in second_rows        
        # Take screenshot of the rejection
        second_page.screenshot(path="/tmp/backend_rejection_220_ephemeral.png")
        print("Saved screenshot to /tmp/backend_rejection_220_ephemeral.png")

