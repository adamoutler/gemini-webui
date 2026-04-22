import pytest
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


@pytest.mark.timeout(60)
def test_renderLauncher_e2e(page, playwright):
    """Test that renderLauncher successfully creates the DOM elements."""
    # Ensure launcher is present
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)

    # Check that connection cards exist
    expect(page.locator(".connection-card").first).to_be_visible(timeout=15000)

    # Check that Quick Connect exists
    expect(page.locator(".quick-connect-bar").first).to_be_visible(timeout=15000)
