import pytest
from playwright.sync_api import expect
import os


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.set_default_timeout(60000)
    page.goto(server, timeout=15000)
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    yield page
    context.close()
    browser.close()


@pytest.mark.timeout(60)
def test_new_connection_clean_startup(page, server):
    """Verify that starting a new connection doesn't produce initialization errors."""
    # Ensure launcher is loaded
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)

    # Wait for the "Start New" button to be visible and click it
    # The 'Start New' button exists on the host cards in the launcher
    start_new_button = page.locator("button.primary", has_text="Start New").first
    expect(start_new_button).to_be_visible(timeout=15000)
    start_new_button.click()

    # Wait for terminal to be visible
    page.wait_for_selector(".xterm-rows", state="visible", timeout=15000)

    # Wait a bit for the output to finish streaming in
    page.wait_for_timeout(3000)

    # Get the text from the terminal
    terminal_text = page.locator(".xterm-rows").inner_text()

    # Take a screenshot for visual proof required by QA gate
    os.makedirs("public/qa-screenshots", exist_ok=True)
    screenshot_path = "public/qa-screenshots/clean_new_connection_proof.png"
    page.screenshot(path=screenshot_path)

    # Assert there are no errors in the output
    assert (
        "ImportProcessor" not in terminal_text
    ), "Found ImportProcessor error in terminal output"
    assert (
        "reality-checker)" not in terminal_text
    ), "Found reality-checker) parsing error in terminal output"
    assert (
        "Keychain initialization" not in terminal_text
    ), "Found Keychain initialization error in terminal output"
    assert (
        "Invalid session identifier" not in terminal_text
    ), "Found Invalid session identifier error in terminal output"
