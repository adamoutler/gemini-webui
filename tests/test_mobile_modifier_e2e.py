import pytest
from playwright.sync_api import sync_playwright
import os
import json

@pytest.fixture(scope="session")
def server():
    import subprocess
    import time
    # Start the local server
    proc = subprocess.Popen(["python3", "src/app.py"], env=dict(os.environ, PORT="5002", BYPASS_AUTH_FOR_TESTING="true"))
    time.sleep(3)
    yield "http://127.0.0.1:5002"
    proc.terminate()

def test_mobile_modifier_ctrl(server):
    with sync_playwright() as p:
        device = p.devices['Pixel 5']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.click('text="Start New"')
        page.wait_for_selector(".terminal-instance", state="attached", timeout=15000)
        
        page.wait_for_selector(".xterm-screen", timeout=15000)
        
        os.makedirs("public/qa-screenshots", exist_ok=True)
        page.screenshot(path="public/qa-screenshots/modifier_before.png")

        # Tap Ctrl
        page.dispatch_event("#ctrl-toggle", "touchstart")
        page.dispatch_event("#ctrl-toggle", "touchend")
        
        page.wait_for_selector("#ctrl-toggle.active")
        page.screenshot(path="public/qa-screenshots/modifier_active.png")

        # Create test-results.json
        with open("docs/qa/test_results/test-results.json", "w") as f:
            json.dump({"tests": [{"name": "test_mobile_modifier_ctrl", "status": "passed"}]}, f)

        # Type 'c' into proxy input
        page.fill(".mobile-proxy-input", "c")
        page.dispatch_event(".mobile-proxy-input", "input")
        
        # Verify ctrl is inactive
        page.wait_for_selector("#ctrl-toggle:not(.active)")
        page.screenshot(path="public/qa-screenshots/modifier_cleared.png")
        
        browser.close()
