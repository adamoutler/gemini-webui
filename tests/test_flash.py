# Resolves Tickets 173, 150, 149, 147, 145, 144, 140, 139, 138
import pytest
import time
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(60000)
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        yield page, server, context
        context.close()
        browser.close()

def test_flash_strictly_on_timestamp_update(page):
    playwright_page, server_url, context = page
    
    # intercept the sessions API to provide predictable last_active timestamps
    session_state = {"last_active": 1000}
    
    def handle_route(route):
        if "/api/management/sessions" in route.request.url:
            if route.request.method == "GET":
                # Mock response
                response_body = [{
                    "tab_id": "test_tab_1",
                    "title": "Test Session",
                    "is_orphaned": False,
                    "last_active": session_state["last_active"],
                    "ssh_dir": "/tmp",
                    "ssh_target": None,
                    "resume": True
                }]
                route.fulfill(json=response_body)
            else:
                route.continue_()
        else:
            route.continue_()
            
    playwright_page.route("**/api/management/sessions*", handle_route)
    
    playwright_page.goto(server_url)
    playwright_page.wait_for_selector(".launcher", state="attached")
    
    # Force a refresh to load initial data
    playwright_page.evaluate('''() => {
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }''')
    
    playwright_page.wait_for_selector(".session-item")
    
    node = playwright_page.locator('.pulse-indicator').first
    
    # Initial load: no flash
    assert 'superbright' not in node.evaluate("el => el.className")
    
    # Refresh with same timestamp: no flash
    playwright_page.evaluate('''() => {
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }''')
    playwright_page.wait_for_timeout(500)
    assert 'superbright' not in node.evaluate("el => el.className")
    
    # Refresh with updated timestamp: flash
    session_state["last_active"] = 2000
    playwright_page.evaluate('''() => {
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }''')
    playwright_page.wait_for_timeout(500)
    assert 'superbright' in node.evaluate("el => el.className")
    
    # Clear the class manually to test that it doesn't get re-added on next refresh without a state change
    node.evaluate("el => el.classList.remove('superbright', 'pulsing')")
    
    # Refresh with same timestamp again: no flash
    playwright_page.evaluate('''() => {
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }''')
    playwright_page.wait_for_timeout(500)
    assert 'superbright' not in node.evaluate("el => el.className")