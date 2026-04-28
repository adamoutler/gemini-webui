import pytest
from playwright.sync_api import expect
import time
import os


@pytest.mark.timeout(60)
def test_get_sessions_timeout_auto_recovery(server, tmp_path, playwright):
    """
    Test that after 5 consecutive get_sessions timeouts, the app clears local storage and reloads.
    """
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))

    page.goto(server)
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=5000)

    # Corrupt local storage
    page.evaluate("""() => {
        localStorage.setItem('geminiResume', 'corrupt_resume_id');
        localStorage.setItem('pinned_tabs', 'corrupt_tabs_data');
        localStorage.setItem('sessionsCache', 'corrupt_cache');
    }""")

    # Verify corruption
    assert page.evaluate("localStorage.getItem('geminiResume')") == "corrupt_resume_id"

    # Mock socket emit to immediately timeout get_sessions
    page.evaluate("""() => {
        const socket = getGlobalSocket();
        const originalEmit = socket.emit;
        socket.emit = function(event, params, callback) {
            if (event === 'get_sessions') {
                if (typeof callback === 'function') {
                    // Send timeout error directly to skip 5s wait
                    console.log('Mocking timeout');
                    callback({ error: "Timeout waiting for get_sessions" });
                }
                return;
            }
            return originalEmit.apply(this, arguments);
        };

        // Expose a function to trigger fetchSessions
        window.triggerMockTimeouts = async () => {
            const dummy = document.createElement('div');
            dummy.id = 'dummy-list';
            document.body.appendChild(dummy);

            const conn = {label: 'local', type: 'local'};
            try {
                for(let i = 0; i < 6; i++) {
                    await fetchSessions('tab_0', conn, 'dummy-list', false, true);
                }
            } catch (e) {
                console.error("Error in mock timeouts:", e);
            }
        };
    }""")

    # Trigger timeouts
    page.evaluate("async () => await window.triggerMockTimeouts()")

    # Verify reloading message
    msg_locator = page.locator(".js-style-7b7303")
    expect(msg_locator).to_have_text(
        "Connection unstable. Local storage cleared. Reloading...", timeout=5000
    )

    # Wait for the page to reload
    page.wait_for_load_state("networkidle")

    # Verify storage is cleared
    assert page.evaluate("localStorage.getItem('geminiResume')") is None
    assert page.evaluate("localStorage.getItem('pinned_tabs')") is None
    assert page.evaluate("localStorage.getItem('sessionsCache')") is None
