import pytest
import re
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    page = context.new_page()
    page.set_default_timeout(60000)
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    page.goto(server, timeout=15000)
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    yield page
    context.close()
    browser.close()


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_connection_health_indicators(page, playwright):
    """Verify that connection health indicators change on failures."""
    # Ensure launcher is loaded
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)

    # At start, since it succeeds, local health should be 🟢
    # Let's wait for the first successful fetch to turn it to green
    local_health = page.locator(
        'div[data-label="local"] .connection-title span[id$="_health_local"]'
    )
    expect(local_health).to_have_text("🟢", timeout=15000)
    expect(local_health).to_have_attribute("data-status", "connected", timeout=15000)

    # Locate the pulse indicator
    pulse_indicator = page.locator(
        'div[data-label="local"] .connection-title div[id$="_pulse_local"]'
    )

    # Mock socket emit to return error
    page.evaluate("""() => {
        const socket = getGlobalSocket();
        window.originalEmit = socket.emit.bind(socket);
        socket.emit = (event, data, callback) => {
            if (event === 'get_sessions') {
                if (callback) callback({ error: "Internal Server Error" });
                return socket;
            }
            return window.originalEmit(event, data, callback);
        };
    }""")

    # Trigger fetchSessions manually on the page for testing to bypass 10s wait
    page.evaluate("""() => {
        const id = activeTabId;
        const sessionListId = `${id}_sessions_local`;
        fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
    }""")

    # Verify the pulse indicator triggers
    expect(pulse_indicator).to_have_class(re.compile(r"pulsing"), timeout=15000)
    expect(pulse_indicator).to_have_class(re.compile(r"superbright"), timeout=15000)

    # 1 failure -> Yellow 🟡
    expect(local_health).to_have_text("🟡", timeout=15000)
    expect(local_health).to_have_attribute("data-status", "degraded", timeout=15000)

    # Trigger again
    page.evaluate("""() => {
        const id = activeTabId;
        const sessionListId = `${id}_sessions_local`;
        fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
    }""")

    # 2 failures -> Red 🔴
    expect(local_health).to_have_text("🔴", timeout=15000)
    expect(local_health).to_have_attribute("data-status", "error", timeout=15000)

    # Remove mock to let it succeed
    page.evaluate("""() => {
        if (window.originalEmit) {
            getGlobalSocket().emit = window.originalEmit;
        }
    }""")

    # Trigger again to recover
    page.evaluate("""() => {
        const id = activeTabId;
        const sessionListId = `${id}_sessions_local`;
        fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
    }""")

    # Success -> Green 🟢
    expect(local_health).to_have_text("🟢", timeout=15000)
    expect(local_health).to_have_attribute("data-status", "connected", timeout=15000)


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_default_health_indicator_grey(server, playwright):
    """Verify that a server defaults to grey (⚪) and correctly turns red on manual failure."""
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    page = context.new_page()
    page.set_default_timeout(60000)
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))

    # Block Socket.io completely to simulate an offline server
    page.route("**/socket.io/*", lambda route: route.abort())
    page.add_init_script("""
        window.WebSocket = class extends WebSocket {
            constructor() {
                throw new Error("Simulated offline WebSocket");
            }
        };
    """)

    page.goto(server, timeout=15000)
    page.wait_for_selector(".launcher", state="attached", timeout=15000)

    local_health = page.locator(
        'div[data-label="local"] .connection-title span[id$="_health_local"]'
    )

    # It should start grey ⚪
    expect(local_health).to_have_text("⚪", timeout=2000)

    # After the 5 second timeout in fetchSessions, it should turn red 🔴
    expect(local_health).to_have_text("🔴", timeout=15000)
    expect(local_health).to_have_attribute("data-status", "error", timeout=15000)

    context.close()
    browser.close()


@pytest.mark.timeout(60)
def test_sync_pulse_with_health_indicator(server, playwright):
    """Verify that calling updateHostHealthIndicator synchronously triggers the pulse animation."""
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    page = context.new_page()
    page.set_default_timeout(60000)
    page.goto(server, timeout=15000)
    page.wait_for_selector(".launcher", state="attached", timeout=15000)

    pulse_indicator = page.locator(
        'div[data-label="local"] .connection-title div[id$="_pulse_local"]'
    )

    # The class stays on the element after animation, so we remove it manually to test the trigger
    page.evaluate("""() => {
        if (typeof activeTabId !== "undefined") {
            const id = activeTabId;
            const pulseId = `${id}_pulse_local`;
            const pulseEl = document.getElementById(pulseId);
            if (pulseEl) pulseEl.classList.remove('pulsing');
        }
    }""")

    expect(pulse_indicator).not_to_have_class(re.compile(r"pulsing"), timeout=15000)

    # Call updateHostHealthIndicator directly
    page.evaluate("""() => {
        if (typeof activeTabId !== "undefined") {
            const id = activeTabId;
            updateHostHealthIndicator(id, 'local', true);
        }
    }""")

    # Verify the pulse indicator triggers immediately
    expect(pulse_indicator).to_have_class(re.compile(r"pulsing"), timeout=15000)
    expect(pulse_indicator).to_have_class(re.compile(r"superbright"), timeout=15000)

    context.close()
    browser.close()
