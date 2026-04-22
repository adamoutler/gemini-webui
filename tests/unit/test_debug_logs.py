import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    yield page
    browser.close()


@pytest.mark.timeout(60)
def test_debug_logging(page, server, playwright):
    logs = []
    page.on("console", lambda msg: logs.append(msg.text))
    page.goto(server)

    # Wait for initial load
    page.wait_for_timeout(2000)
    page.wait_for_function("typeof window.setDebug === 'function'")

    # Take screenshot of settings
    page.evaluate("openSettings()")
    page.wait_for_selector("#settings-modal", state="visible")
    page.evaluate(
        "document.querySelector('#settings-modal .modal-content').scrollBy(0, 1000)"
    )
    page.wait_for_timeout(1000)
    page.screenshot(path="public/qa-screenshots/debug_settings.png")
    page.evaluate("closeSettings()")
    page.wait_for_selector("#settings-modal", state="hidden")

    initial_log_count = len(logs)

    # Enable debug logging
    page.evaluate("window.setDebug(true)")
    page.wait_for_timeout(2000)

    # Check if debug logs increased significantly
    enabled_log_count = len(logs)
    assert (
        enabled_log_count > initial_log_count
    ), "No debug logs appeared after enabling"

    # Disable debug logging
    page.evaluate("window.setDebug(false)")
    logs.clear()  # clear logs
    page.wait_for_timeout(2000)

    disabled_log_count = len([l for l in logs if "Verbose debugging" not in l])
    assert disabled_log_count < 10, "Too many logs appeared after disabling"

    with open("docs/qa-images/test_debug_logs_output.txt", "w") as f:
        f.write(
            f"Test completed successfully. Debug logging toggle works. Enabled logs: {enabled_log_count - initial_log_count}, Disabled logs: {disabled_log_count}"
        )
