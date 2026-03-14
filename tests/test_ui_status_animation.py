import pytest
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


@pytest.mark.timeout(60)
def test_status_indicator_animation(page):
    playwright_page, server_url, context = page

    # We need to simulate a session so it shows up in "Backend Managed Sessions"
    # First, let's load the app and start a session
    playwright_page.goto(server_url)
    playwright_page.wait_for_selector(".launcher", state="attached")

    # Click on the Connect button for the local host
    local_connect_btn = playwright_page.locator(
        'div[data-label="local"] button:has-text("Start New")'
    ).first
    local_connect_btn.click()

    # Wait for the terminal to appear
    playwright_page.wait_for_selector(".terminal-instance", state="attached")

    # Now click the New Tab button (+) to go back to the launcher
    new_tab_btn = playwright_page.locator("#new-tab-btn")
    new_tab_btn.click()

    # Wait for launcher again
    playwright_page.wait_for_selector(".launcher", state="attached")

    # Check that it appears in backend sessions and has status-node and status-online
    node = playwright_page.locator(".status-node.status-online").first
    expect(node).to_be_attached(timeout=15000)

    # Ensure there is a flash class logic built-in, but initially it won't have flash unless it updates
    assert node.count() > 0

    # Check CSS properties to ensure no clipping
    margin_top = node.evaluate("el => window.getComputedStyle(el).marginTop")
    margin_bottom = node.evaluate("el => window.getComputedStyle(el).marginBottom")
    margin_left = node.evaluate("el => window.getComputedStyle(el).marginLeft")

    assert (
        int(margin_top.replace("px", "")) >= 4
    ), "Spinner top margin is too small, will clip"
    assert (
        int(margin_bottom.replace("px", "")) >= 4
    ), "Spinner bottom margin is too small, will clip"
    assert (
        int(margin_left.replace("px", "")) >= 4
    ), "Spinner left margin is too small, will clip"


@pytest.mark.timeout(60)
def test_status_animation_dom_persistence(page):
    playwright_page, server_url, context = page

    # Load app and start a session
    playwright_page.goto(server_url)
    playwright_page.wait_for_selector(".launcher", state="attached")

    # Click to connect local host
    local_connect_btn = playwright_page.locator(
        'div[data-label="local"] button:has-text("Start New")'
    ).first
    local_connect_btn.click()

    # Wait for terminal to appear
    playwright_page.wait_for_selector(".terminal-instance", state="attached")

    # Click New Tab button
    new_tab_btn = playwright_page.locator("#new-tab-btn")
    new_tab_btn.click()

    # Wait for launcher again
    playwright_page.wait_for_selector(".launcher", state="attached")

    # Wait for the backend session item to appear
    session_item = playwright_page.locator(
        ".backend-sessions-container .session-item"
    ).first
    expect(session_item).to_be_attached(timeout=15000)

    html_before = session_item.evaluate("el => el.outerHTML")
    print(f"HTML BEFORE: {html_before}")

    # Add a custom attribute to the DOM node to track if it gets replaced
    session_item.evaluate("""el => el.setAttribute('data-test-marker', 'persisted')""")

    marker_before = session_item.evaluate("el => el.getAttribute('data-test-marker')")
    print(f"MARKER BEFORE REFRESH: {marker_before}")

    # Trigger refresh manually rather than waiting 5 seconds
    playwright_page.evaluate("""() => {
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }""")

    # Wait a bit for the async fetch to complete
    playwright_page.wait_for_timeout(2000)

    # Re-evaluate the custom attribute on the first item
    html_after = playwright_page.locator(
        ".backend-sessions-container .session-item"
    ).first.evaluate("el => el.outerHTML")
    print(f"HTML AFTER: {html_after}")

    marker = playwright_page.locator(
        ".backend-sessions-container .session-item"
    ).first.evaluate("el => el.getAttribute('data-test-marker')")
    assert (
        marker == "persisted"
    ), "DOM node was replaced upon reload, resetting animation state!"


def test_status_flash_on_update(page):
    playwright_page, server_url, context = page

    # Start app and create a session
    playwright_page.goto(server_url, timeout=15000)
    playwright_page.wait_for_selector(".launcher", state="attached", timeout=15000)

    local_connect_btn = playwright_page.locator(
        'div[data-label="local"] button:has-text("Start New")'
    ).first
    local_connect_btn.click()
    playwright_page.wait_for_selector(
        ".terminal-instance", state="attached", timeout=15000
    )

    new_tab_btn = playwright_page.locator("#new-tab-btn")
    new_tab_btn.click()
    playwright_page.wait_for_selector(".launcher", state="attached", timeout=15000)

    # Wait for the backend session item
    session_item = playwright_page.locator(
        ".backend-sessions-container .session-item"
    ).first
    expect(session_item).to_be_attached(timeout=10000)

    node = session_item.locator(".status-node")
    expect(node).to_be_attached()

    # We want to intercept the next fetch to get_management_sessions via WebSocket
    playwright_page.evaluate("""() => {
        const socket = getGlobalSocket();
        const originalEmit = socket.emit.bind(socket);
        socket.emit = (event, callback) => {
            if (event === 'get_management_sessions') {
                // We need to return a session that matches the existing one but with an updated time
                // To do this simply, we will intercept and return the actual data + 100 on last_active
                // However, since we mock it synchronously, we can just grab what's in the DOM
                const activeTab = document.querySelector('.tab-instance.active');
                if (activeTab) {
                    const id = activeTab.id.replace('_instance', '');
                    const existingRow = document.querySelector(`#${id}_backend_sessions .session-item`);
                    if (existingRow && existingRow.id) {
                        const tabId = existingRow.id.replace(`managed-session-${id}-`, '');
                        callback([{
                            tab_id: tabId,
                            title: "Test",
                            is_orphaned: false,
                            last_active: Date.now() / 1000 + 100 // Future time to force flash
                        }]);
                        return socket;
                    }
                }
                callback([]);
                return socket;
            }
            return originalEmit(event, callback);
        };
    }""")

    # Trigger refresh
    playwright_page.evaluate("""() => {
        const activeTab = document.querySelector('.tab-instance.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            console.log("Triggering refresh for " + id);
            refreshBackendSessionsList(id);
        } else {
            console.log("No active tab found");
        }
    }""")

    # Wait to ensure the route had time to trigger
    playwright_page.wait_for_timeout(1000)

    # The node should get the 'flash' class momentarily
    import re

    expect(node).to_have_class(re.compile(r".*\bflash\b.*"), timeout=5000)
