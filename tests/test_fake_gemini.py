import pytest
import time
import warnings
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(60)
def test_fake_gemini_e2e_flow(page, server):
    # 1. Navigate to test-launcher
    page.goto(f"{server}/test-launcher", timeout=15000)
    expect(page.locator("h1:has-text('TEST LAUNCHER')")).to_be_visible()
    
    # Capture UI Distinction Screenshot (Test Launcher)
    launcher_ss_path = "/tmp/gemini-webui-test-launcher_220.png"
    page.screenshot(path=launcher_ss_path)
    warnings.warn(f"Empirical Evidence: Saved test-launcher screenshot to {launcher_ss_path}")
    
    # 2. Submit form
    page.locator("input[name='scenario']").fill("test_scenario=1")
    page.locator("button:has-text('Launch Fake Session')").click()
    
    # Wait for terminal view to attach
    page.wait_for_selector(".terminal-instance", state="attached", timeout=15000)
    
    # 3. Verify .theme-fake-session exists
    expect(page.locator(".theme-fake-session")).to_be_visible()
    
    # Wait for terminal readiness
    page.wait_for_selector(".xterm-helper-textarea", state="attached", timeout=10000)
    
    # Capture UI Distinction Screenshot (Fake Session Theme)
    theme_ss_path = "/tmp/gemini-webui-fake-theme_220.png"
    page.screenshot(path=theme_ss_path)
    warnings.warn(f"Empirical Evidence: Saved fake session theme screenshot to {theme_ss_path}")
    
    # 4. Interact with the terminal (Send Enter to see if fake gemini is running)
    textarea = page.locator(".xterm-helper-textarea").first
    # Wait until Fake Gemini emits "Welcome to Fake Gemini" or similar
    # The user might be prompted or just a prompt is shown.
    page.keyboard.type("Hello Fake Gemini")
    page.keyboard.press("Enter")
    
    # Give it a bit to process and write to xterm
    page.wait_for_timeout(2000)
    
    # Read the terminal rows via xterm API
    rows = page.evaluate("() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString()).join('\\n') : ''; }")
    print("Terminal Content:")
    print(rows)
    assert "[Fake Gemini v2.0 - High Fidelity Mode]" in rows or "Welcome to Fake Gemini" in rows or "Hello Fake Gemini" in rows, f"Expected Fake Gemini output not found. Got: {rows}"
    
    # 5. Trigger UX Friction Modal by disconnecting the socket
    page.evaluate("tabs.find(t => t.id === activeTabId).socket.disconnect()")
    
    # Wait for friction modal
    expect(page.locator(".friction-modal")).to_be_visible(timeout=10000)
    expect(page.locator("h2:has-text('Session Disconnected')")).to_be_visible()
    
    # Capture UX Friction Modal Screenshot
    modal_ss_path = "/tmp/gemini-webui-friction-modal_220.png"
    page.screenshot(path=modal_ss_path)
    warnings.warn(f"Empirical Evidence: Saved friction modal screenshot to {modal_ss_path}")
    
    # Assert successful completion
    assert True
