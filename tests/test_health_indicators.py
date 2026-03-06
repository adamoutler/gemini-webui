import pytest
import time
import re
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
def test_connection_health_indicators(page):
    """Verify that connection health indicators change on failures."""
    # Ensure launcher is loaded
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=5000)
    
    # At start, since it succeeds, local health should be 🟢
    # Let's wait for the first successful fetch to turn it to green
    local_health = page.locator('div[data-label="local"] .connection-title span[id$="_health_local"]')
    expect(local_health).to_have_text("🟢", timeout=5000)
    expect(local_health).to_have_attribute("data-status", "connected", timeout=5000)
    
    # Locate the pulse indicator
    pulse_indicator = page.locator('div[data-label="local"] .connection-title div[id$="_pulse_local"]')

    # Mock /api/sessions to return 500
    def handle_route(route):
        route.fulfill(status=500, body="Internal Server Error")
        
    page.route("**/api/sessions*", handle_route)
    
    # Trigger fetchSessions manually on the page for testing to bypass 10s wait
    page.evaluate('''() => {
        const id = activeTabId;
        const sessionListId = `${id}_sessions_local`;
        fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
    }''')
    
    # Verify the pulse indicator triggers
    expect(pulse_indicator).to_have_class(re.compile(r"pulsing"), timeout=5000)

    # 1 failure -> Yellow 🟡
    expect(local_health).to_have_text("🟡", timeout=5000)
    expect(local_health).to_have_attribute("data-status", "degraded", timeout=5000)
    
    # Trigger again
    page.evaluate('''() => {
        const id = activeTabId;
        const sessionListId = `${id}_sessions_local`;
        fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
    }''')
    
    # 2 failures -> Red 🔴
    expect(local_health).to_have_text("🔴", timeout=5000)
    expect(local_health).to_have_attribute("data-status", "error", timeout=5000)
    
    # Remove mock to let it succeed
    page.unroute("**/api/sessions*")
    
    # Trigger again to recover
    page.evaluate('''() => {
        const id = activeTabId;
        const sessionListId = `${id}_sessions_local`;
        fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
    }''')
    
    # Success -> Green 🟢
    expect(local_health).to_have_text("🟢", timeout=5000)
    expect(local_health).to_have_attribute("data-status", "connected", timeout=5000)

@pytest.mark.prone_to_timeout
@pytest.mark.timeout(20)
def test_default_health_indicator_grey(server):
    """Verify that a server defaults to grey (⚪) and correctly turns red on manual failure."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        # Mock /api/sessions to fail IMMEDIATELY on first load to simulate offline server
        def handle_route(route):
            route.fulfill(status=500, body="Internal Server Error")
        page.route("**/api/sessions*", handle_route)
        
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher", state="attached", timeout=15000)
        
        # Check that local health indicator is ⚪ (grey)
        local_health = page.locator('div[data-label="local"] .connection-title span[id$="_health_local"]')
        expect(local_health).to_have_text("⚪", timeout=5000)
        expect(local_health).to_have_attribute("data-status", "offline", timeout=5000)
        
        # Check that it turns 🔴 when doing a manual non-cached fetch
        page.evaluate('''() => {
            if (typeof activeTabId !== "undefined") {
                const id = activeTabId;
                const sessionListId = `${id}_sessions_local`;
                fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
            }
        }''')
        
        expect(local_health).to_have_text("🔴", timeout=5000)
        expect(local_health).to_have_attribute("data-status", "error", timeout=5000)

        context.close()
        browser.close()

@pytest.mark.timeout(10)
def test_sync_pulse_with_health_indicator(server):
    """Verify that calling updateHostHealthIndicator synchronously triggers the pulse animation."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher", state="attached", timeout=15000)
        
        pulse_indicator = page.locator('div[data-label="local"] .connection-title div[id$="_pulse_local"]')
        
        # The class stays on the element after animation, so we remove it manually to test the trigger
        page.evaluate('''() => {
            if (typeof activeTabId !== "undefined") {
                const id = activeTabId;
                const pulseId = `${id}_pulse_local`;
                const pulseEl = document.getElementById(pulseId);
                if (pulseEl) pulseEl.classList.remove('pulsing');
            }
        }''')
        
        expect(pulse_indicator).not_to_have_class(re.compile(r"pulsing"), timeout=5000)
        
        # Call updateHostHealthIndicator directly
        page.evaluate('''() => {
            if (typeof activeTabId !== "undefined") {
                const id = activeTabId;
                updateHostHealthIndicator(id, 'local', true);
            }
        }''')
        
        # Verify the pulse indicator triggers immediately
        expect(pulse_indicator).to_have_class(re.compile(r"pulsing"), timeout=1000)

        context.close()
        browser.close()
