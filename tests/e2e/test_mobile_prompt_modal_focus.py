import os
import pytest
from playwright.sync_api import expect


@pytest.fixture
def mobile_context(playwright):
    iphone_13 = playwright.devices["iPhone 13"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**iphone_13)
    yield context
    browser.close()


def test_mobile_prompt_modal_focus(server, mobile_context):
    page = mobile_context.new_page()
    page.goto(server)

    # Wait for UI to load
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)

    # Emulate mobile explicitly
    page.evaluate("document.documentElement.classList.add('is-mobile')")

    # Start session to ensure the terminal/mobile proxies are fully initialized
    page.click("#new-tab-btn")
    page.click("text=Start New")
    page.wait_for_selector(".xterm-screen", timeout=15000)
    page.wait_for_timeout(1000)

    # Open the Add Prompt Modal directly via JS to avoid hunting for the UI button
    page.evaluate("openAddPromptModal()")
    page.wait_for_selector("#add-prompt-modal", state="visible", timeout=5000)

    # Wait for the animation
    page.wait_for_timeout(1000)

    os.makedirs("docs/qa-images", exist_ok=True)
    page.screenshot(path="docs/qa-images/modal-tap-before.png")

    # Click the prompt textarea
    prompt_textarea = page.locator("#new-prompt-text")
    prompt_textarea.click()
    page.wait_for_timeout(500)

    # Take screenshot of the focus state
    page.screenshot(path="docs/qa-images/modal-tap-after.png")

    # The proxy input should NOT be focused
    proxy_is_focused = page.evaluate(
        "document.activeElement.classList.contains('mobile-text-area')"
    )
    assert (
        not proxy_is_focused
    ), "The hidden mobile proxy stole focus from the modal textarea!"

    # The modal textarea SHOULD be focused
    modal_is_focused = page.evaluate("document.activeElement.id === 'new-prompt-text'")
    assert modal_is_focused, "The prompt textarea did not receive focus!"
