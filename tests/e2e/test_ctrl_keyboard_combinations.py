# Resolves Ticket GEMWEBUI-176
import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module")
def browser_context(playwright):
    playwright = playwright
    if True:
        device = playwright.devices["Desktop Chrome"]
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        context.close()
        browser.close()


@pytest.fixture(scope="function")
def page(server, browser_context):
    page = browser_context.new_page()
    page.set_default_timeout(120000)
    page.goto(server, timeout=15000)
    page.locator("#new-tab-btn").click()
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)
    yield page
    page.close()


def test_physical_keyboard_combinations(page):
    # Override emitPtyInput to catch what is being sent
    page.evaluate("""() => {
        window.sentInputs = [];
        const originalEmit = window.emitPtyInput;
        window.emitPtyInput = function(tab, data) {
            window.sentInputs.push(data);
            if (originalEmit) originalEmit(tab, data);
        };
    }""")

    # Wait for the focus to settle on textarea
    textarea = page.locator(".xterm-helper-textarea").last

    # Click to ensure focus
    textarea.wait_for(state="attached", timeout=30000)
    textarea.focus()

    # Press Ctrl+C
    page.keyboard.press("Control+c")

    # Press Ctrl+D
    page.keyboard.press("Control+d")

    # Press Ctrl+L
    page.keyboard.press("Control+l")

    # Wait for processing
    page.wait_for_timeout(500)

    # Check what was sent
    sent = page.evaluate("window.sentInputs")
    print("Sent inputs:", sent)

    # Ctrl+C is \x03, Ctrl+D is \x04, Ctrl+L is \x0c
    assert "\x03" in sent, "Ctrl+C was not sent"
    assert "\x04" in sent, "Ctrl+D was not sent"
    assert "\x0c" in sent, "Ctrl+L was not sent"

    # Assert that no local auto-correct textbox is focused or actively composing text.
    # The normal textarea is focused, but it shouldn't have .is-composing active.
    is_composing = page.evaluate(
        "document.activeElement.classList.contains('is-composing')"
    )
    assert (
        not is_composing
    ), "The auto-correct STT overlay should not be active when pressing modifier keys."
