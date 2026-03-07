import pytest
from playwright.sync_api import sync_playwright, expect
import time

def test_flash_strictly_on_timestamp_update(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
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
                
        page.route("**/api/management/sessions*", handle_route)
        
        page.goto(server)
        page.wait_for_selector(".launcher", state="attached")
        
        # Force a refresh to load initial data
        page.evaluate('''() => {
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) {
                const id = activeTab.id.replace('_instance', '');
                refreshBackendSessionsList(id);
            }
        }''')
        
        page.wait_for_selector("#managed-session-test_tab_1")
        
        node = page.locator('.status-node')
        
        # Initial load: no flash
        assert 'flash' not in node.evaluate("el => el.className")
        
        # Refresh with same timestamp: no flash
        page.evaluate('''() => {
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) {
                const id = activeTab.id.replace('_instance', '');
                refreshBackendSessionsList(id);
            }
        }''')
        page.wait_for_timeout(500)
        assert 'flash' not in node.evaluate("el => el.className")
        
        # Refresh with updated timestamp: flash
        session_state["last_active"] = 2000
        page.evaluate('''() => {
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) {
                const id = activeTab.id.replace('_instance', '');
                refreshBackendSessionsList(id);
            }
        }''')
        page.wait_for_timeout(500)
        assert 'flash' in node.evaluate("el => el.className")
        
        # Refresh with same timestamp again: no flash
        page.evaluate('''() => {
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) {
                const id = activeTab.id.replace('_instance', '');
                refreshBackendSessionsList(id);
            }
        }''')
        page.wait_for_timeout(500)
        assert 'flash' not in node.evaluate("el => el.className")
        
        browser.close()
