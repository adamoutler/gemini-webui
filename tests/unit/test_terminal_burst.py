import pytest
import time
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="function")
def desktop_page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    page.goto(server, timeout=15000)
    yield page
    context.close()
    browser.close()


def test_terminal_burst_scroll(desktop_page, playwright):
    # Wait for the UI
    desktop_page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )

    from playwright.sync_api import expect

    # Click "Start New" on local (first card) in the ACTIVE tab
    try:
        btns = desktop_page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=10000)
        btns.first.click()
    except Exception as e:
        print(f"Failed to click Start New: {e}")

    # Wait for terminal to be active
    expect(desktop_page.locator("#active-connection-info")).to_be_visible(timeout=10000)

    # Wait a bit for initialization
    time.sleep(2)

    # Inject a function to send a command and check scroll after it finishes
    script = """
    async () => {
        return new Promise(resolve => {
            const tab = tabs.find(t => t.state === 'terminal');
            if (!tab || !tab.term) {
                resolve({ error: "No active terminal" });
                return;
            }

            // Simulate single massive ingestion that wraps extensively by simulating socket events
            const ptyOutputListeners = tab.socket.listeners ? tab.socket.listeners('pty-output') : [];
            const ptyOutputHandler = ptyOutputListeners.length > 0 ? ptyOutputListeners[0] : null;

            if (!ptyOutputHandler) {
                resolve({ error: "No pty-output listener found" });
                return;
            }

            let i = 0;
            const chunkSize = 50;

            function emitChunk() {
                if (i >= 500) {
                    setTimeout(() => {
                        const buffer = tab.term.buffer.active;
                        resolve({
                            viewportY: buffer.viewportY,
                            baseY: buffer.baseY,
                            length: buffer.length
                        });
                    }, 500);
                    return;
                }

                let text = "";
                for(let j = 0; j < chunkSize; j++) {
                    text += `Line ${i+j}: ` + "A".repeat(2000) + `\\r\\n`;
                }
                i += chunkSize;

                ptyOutputHandler({ output: text });
                fitTerminal(tab);
                setTimeout(emitChunk, 5);
            }

            emitChunk();
            });    }
    """
    result = desktop_page.evaluate(script)

    print(f"Result: {result}")
    assert "error" not in result, result["error"]

    # If the bug exists, viewportY will be 0 or very small compared to baseY
    # We want viewportY to be equal to baseY (or very close to it)
    viewport_y = result["viewportY"]
    base_y = result["baseY"]
    length = result["length"]

    assert base_y > 0, "Terminal buffer did not grow"

    # It should not have reset to 0
    assert viewport_y > 0, "Terminal viewport reset to 0 (top of buffer)!"

    # It should be at the bottom (viewportY == baseY)
    assert (
        viewport_y == base_y
    ), f"Terminal did not stay at the bottom. viewportY={viewport_y}, baseY={base_y}"
