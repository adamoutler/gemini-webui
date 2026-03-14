from playwright.sync_api import sync_playwright, expect


def test_theory(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher", state="attached", timeout=15000)

        # Intercept socket emit to simulate failure
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

        # Initially red because the websocket mock returns an explicit error
        expect(local_health).to_have_text("🔴", timeout=5000)

        page.evaluate("""() => {
            if (typeof activeTabId !== "undefined") {
                const id = activeTabId;
                const sessionListId = `${id}_sessions_local`;
                fetchSessions(id, {label: 'local', type: 'local'}, sessionListId, false, false);
            }
        }""")

        # It should become red after the manual fetch fails
        expect(local_health).to_have_text("🔴", timeout=5000)
        context.close()
        browser.close()
