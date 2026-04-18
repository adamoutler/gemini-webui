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


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_esc_dismiss_settings(page, playwright):
    """Verify pressing Escape closes the Settings modal."""
    # Open settings
    page.locator('button[data-onclick="openSettings()"]').click()
    expect(page.locator("#settings-modal")).to_be_visible(timeout=15000)

    # Press Escape
    page.keyboard.press("Escape")

    # Verify settings is closed (display: none)
    expect(page.locator("#settings-modal")).to_be_hidden(timeout=15000)


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_esc_dismiss_file_transfer(page, playwright):
    """Verify pressing Escape closes the File Transfer modal."""
    # Start a terminal to ensure the Files button appears (or it might be visible anyway)
    # Actually, the Files button is in #active-connection-info which is visible when a terminal is active
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Click Files button
    page.locator('button:has-text("Files")').click()
    expect(page.locator("#file-transfer-modal")).to_be_visible(timeout=15000)

    page.wait_for_timeout(500)
    # Ensure terminal doesn't steal focus by clicking the modal background
    page.locator("#file-transfer-modal").click(position={"x": 5, "y": 5})
    # Press Escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Verify it is closed
    expect(page.locator("#file-transfer-modal")).to_be_hidden(timeout=15000)


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_esc_dismiss_launcher(page, playwright):
    """Verify pressing Escape on the launcher returns to an active tab if one exists."""
    # Start a terminal session first
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Get the ID of the first tab to verify we return to it
    # We can check the active tab's title or terminal visibility
    expect(page.locator(".terminal-instance").first).to_be_visible(timeout=15000)

    # Click + New to open the launcher in a new tab
    page.locator("#new-tab-btn").click()

    # Verify we are on the launcher
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)
    expect(page.locator("#active-connection-info")).to_be_hidden(timeout=15000)

    # Store tab count
    tabs_count = page.locator(".tab").count()
    assert tabs_count > 1

    # Press Escape
    page.keyboard.press("Escape")

    # Verify the launcher tab is NOT closed (as per new requirements)
    page.wait_for_timeout(1000)  # wait to ensure no close happens
    expect(page.locator(".tab")).to_have_count(tabs_count)
    expect(page.locator(".launcher").first).to_be_hidden()
    expect(page.locator(".terminal-instance").first).to_be_visible()
