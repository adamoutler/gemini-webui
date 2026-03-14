import pytest
from playwright.sync_api import sync_playwright, expect
import json

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

def test_quick_connect_default_port(page, server):
    """Verify that user@host without port creates a target without port."""
    # Wait for the quick connect bar to appear
    expect(page.locator('.quick-connect-bar').first).to_be_visible(timeout=15000)
    
    # Find the quick connect input
    page.locator(".quick-connect-input").first.fill("user@testhost")
    
    # We will mock the /api/hosts POST request to inspect the payload
    host_payload = None
    def handle_route(route):
        nonlocal host_payload
        if route.request.method == "POST":
            host_payload = json.loads(route.request.post_data)
            route.fulfill(status=200, json={"success": True})
        else:
            route.continue_()
            
    page.route("**/api/hosts", handle_route)
    
    # Click the Connect button
    page.locator(".quick-connect-bar button").filter(has_text="Connect").first.click()
    
    page.wait_for_timeout(1000)
    
    assert host_payload is not None, "API call to /api/hosts was not intercepted"
    assert host_payload["target"] == "user@testhost"

def test_quick_connect_custom_port(page, server):
    """Verify that user@host:port creates a target with the custom port."""
    expect(page.locator('.quick-connect-bar').first).to_be_visible(timeout=15000)
    
    page.locator(".quick-connect-input").first.fill("user@testhost:2222")
    
    host_payload = None
    def handle_route(route):
        nonlocal host_payload
        if route.request.method == "POST":
            host_payload = json.loads(route.request.post_data)
            route.fulfill(status=200, json={"success": True})
        else:
            route.continue_()
            
    page.route("**/api/hosts", handle_route)
    
    page.locator(".quick-connect-bar button").filter(has_text="Connect").first.click()
    
    page.wait_for_timeout(1000)
    
    assert host_payload is not None, "API call to /api/hosts was not intercepted"
    assert host_payload["target"] == "user@testhost:2222"
