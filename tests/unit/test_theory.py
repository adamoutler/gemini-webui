import pytest
from playwright.sync_api import expect


@pytest.mark.timeout(60)
def test_theory(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto(server, timeout=15000)
    page.wait_for_selector(".launcher", state="attached", timeout=15000)

    # Intercept socket emit to simulate failure for the next poll
    page.evaluate("""() => {
        const socket = getGlobalSocket();
        const originalEmit = socket.emit.bind(socket);
        socket.emit = (event, data, callback) => {
            if (event === 'get_sessions') {
                if (callback) callback({ error: "Internal Server Error" });
                return socket;
            }
            return originalEmit(event, data, callback);
        };
    }""")

    local_health = page.locator(
        'div[data-label="local"] .connection-title span[id$="_health_local"]'
    )

    # Polling happens every 5-10s, so we give it 15s to turn degraded
    expect(local_health).to_have_text("🟡", timeout=15000)

    browser.close()
