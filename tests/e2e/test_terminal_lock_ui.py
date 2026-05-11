import os
import pytest
from playwright.sync_api import expect


@pytest.mark.timeout(60)
def test_terminal_lock_ui(server, playwright):
    browser = playwright.chromium.launch(headless=True)

    # Test Desktop
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    page.goto(server)

    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    page.click("text=Start New")
    page.wait_for_selector(".xterm-screen")
    page.wait_for_timeout(1000)

    os.makedirs("docs/qa-images", exist_ok=True)
    page.screenshot(path="docs/qa-images/lock-before.png")

    # Simulate backend sending lock state
    page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        // Force the mock to accept the callback, socket._callbacks handles it in socketio
        // But the easiest way to test the UI response to the socket event is to emit it
        // to the client's own socket if it loops back, but socket.io client doesn't loop back.
        // We'll call the exact handler directly:
        const listeners = tab.socket.listeners("lock_state_changed");
        if (listeners.length > 0) {
            listeners[0]({locked: true, job_name: 'QA Lock Test'});
        }
    }""")

    page.wait_for_selector(".terminal-lock-overlay:not(.hidden)")
    expect(page.locator(".lock-title")).to_contain_text("Automation in Progress")
    expect(page.locator(".lock-job-name")).to_contain_text("Running: QA Lock Test")

    # Ensure terminal is blurred
    is_blurred = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        const termDiv = document.getElementById("rolling-log-" + tab.id);
        return termDiv.style.filter.includes("blur");
    }""")
    assert is_blurred, "Terminal is not blurred!"

    # Try typing into terminal - it should be blocked
    # (Input blocking is done by `tab.isLocked = true` inside `pty.js` `emitPtyInput`)

    # Take active lock desktop screenshot
    page.screenshot(path="docs/qa-images/responsive-desktop-locked.png")

    # Click emergency unlock
    page.click(".btn-emergency-stop")

    # Wait for the overlay to disappear (via socket round trip!)
    page.wait_for_selector(".terminal-lock-overlay.hidden", state="attached")

    page.screenshot(path="docs/qa-images/lock-unlocked.png")

    # Now test mobile explicitly
    mobile_device = playwright.devices["iPhone 13"]
    mobile_context = browser.new_context(**mobile_device)
    mobile_page = mobile_context.new_page()
    mobile_page.goto(server)

    mobile_page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    mobile_page.evaluate("document.documentElement.classList.add('is-mobile')")
    mobile_page.evaluate("startSession('local', '', '', 'new')")
    mobile_page.wait_for_selector(".xterm-screen")
    mobile_page.wait_for_timeout(1000)

    # Simulate backend sending lock state
    mobile_page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        const listeners = tab.socket.listeners("lock_state_changed");
        if (listeners.length > 0) {
            listeners[0]({locked: true, job_name: 'Mobile QA Lock Test'});
        }
    }""")

    mobile_page.wait_for_selector(".terminal-lock-overlay:not(.hidden)")
    mobile_page.screenshot(path="docs/qa-images/responsive-mobile-locked.png")

    mobile_context.close()
    context.close()
    browser.close()
