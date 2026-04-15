# Resolves Tickets 173, 150, 149, 147, 145, 144, 140, 139, 138
import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    if True:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(5000)
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        yield page, server, context
        context.close()
        browser.close()


def test_flash_strictly_on_timestamp_update(page):
    playwright_page, server_url, context = page

    # intercept the sessions API to provide predictable last_active timestamps
    session_state = {"last_active": 1000}

    playwright_page.goto(server_url)
    playwright_page.wait_for_selector(".tab-instance.active", state="attached")

    # Click + New to ensure we are on the connection launcher, in case a terminal was auto-resumed
    playwright_page.click("#new-tab-btn")
    playwright_page.wait_for_selector(
        ".tab-instance.active:not(.terminal)", state="attached", timeout=2000
    )

    # Wait for getGlobalSocket to be available
    playwright_page.wait_for_function(
        "typeof getGlobalSocket === 'function' && getGlobalSocket() !== null"
    )

    # Expose state to window so we can control it from Python
    playwright_page.evaluate("window._testLastActive = 1000")

    # Mock socket.emit for get_management_sessions
    playwright_page.evaluate("""() => {
        const socket = getGlobalSocket();
        if (!socket) return;
        const originalEmit = socket.emit.bind(socket);
        socket.emit = (event, ...args) => {
            if (event === 'get_management_sessions') {
                const callback = args[0];
                if (typeof callback === 'function') {
                    callback([{
                        "tab_id": "test_tab_1",
                        "title": "Test Session",
                        "is_orphaned": false,
                        "last_active": window._testLastActive,
                        "ssh_dir": "/tmp",
                        "ssh_target": null,
                        "resume": true
                    }]);
                }
                return socket;
            }
            return originalEmit(event, ...args);
        };
    }""")

    # Force a refresh to load initial data
    playwright_page.evaluate("""() => {
        const activeTab = document.querySelector('.tab-instance.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }""")

    try:
        playwright_page.wait_for_selector(
            "div[id*='-test_tab_1']", state="attached", timeout=2000
        )
    except Exception as e:
        print(f"FAILED TO FIND ELEMENT. HTML: {playwright_page.content()}")
        raise e

    node = playwright_page.locator("div[id*='-test_tab_1'] .status-node").first

    # Initial load: flashes because we've never seen it before
    assert "flash" in node.evaluate("el => el.className")

    # Clear the class manually
    node.evaluate("el => el.classList.remove('flash')")

    # Refresh with same timestamp: no flash
    playwright_page.evaluate("""() => {
        const activeTab = document.querySelector('.tab-instance.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }""")
    playwright_page.wait_for_timeout(500)
    assert "flash" not in node.evaluate("el => el.className")

    # Refresh with updated timestamp: flash
    playwright_page.evaluate("window._testLastActive = 2000")
    playwright_page.evaluate("""() => {
        const activeTab = document.querySelector('.tab-instance.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }""")
    playwright_page.wait_for_timeout(500)
    assert "flash" in node.evaluate("el => el.className")

    # Clear the class manually to test that it doesn't get re-added on next refresh without a state change
    node.evaluate("el => el.classList.remove('flash')")

    # Refresh with same timestamp again: no flash
    playwright_page.evaluate("""() => {
        const activeTab = document.querySelector('.tab-instance.active');
        if (activeTab) {
            const id = activeTab.id.replace('_instance', '');
            refreshBackendSessionsList(id);
        }
    }""")
    playwright_page.wait_for_timeout(500)
    assert "flash" not in node.evaluate("el => el.className")
