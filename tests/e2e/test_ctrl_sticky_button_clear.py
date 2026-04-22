# Resolves Ticket GEMWEBUI-175
import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def browser_context(playwright):
    playwright = playwright
    device = playwright.devices["Pixel 5"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**device)
    yield context
    context.close()
    browser.close()


@pytest.fixture(scope="function")
def mobile_page(server, browser_context, playwright):
    page = browser_context.new_page()
    page.set_default_timeout(60000)
    page.goto(server, timeout=15000)
    page.locator("#new-tab-btn").click()
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)
    expect(page.locator("#mobile-controls")).to_be_visible(timeout=15000)
    yield page
    page.close()


import re


@pytest.mark.timeout(60)
def test_ctrl_clears_on_control_button(mobile_page, playwright):
    # Tap the software Ctrl button
    mobile_page.locator("#ctrl-toggle").click()

    # Verify it has the active class
    expect(mobile_page.locator("#ctrl-toggle")).to_have_class(re.compile(r".*active.*"))

    # Tap the Tab button (let's use text selector for Tab since it's just .control-btn)
    mobile_page.locator('div.control-btn:has-text("Tab")').click()

    # Verify Ctrl is no longer active
    expect(mobile_page.locator("#ctrl-toggle")).not_to_have_class(
        re.compile(r".*active.*")
    )


@pytest.mark.timeout(60)
def test_ctrl_clears_on_paste(mobile_page, playwright):
    # Tap the software Ctrl button
    mobile_page.locator("#ctrl-toggle").click()

    expect(mobile_page.locator("#ctrl-toggle")).to_have_class(re.compile(r".*active.*"))

    # Find the active tab ID
    active_tab_id = mobile_page.evaluate("sessionStorage.getItem('gemini_active_tab')")
    textarea = mobile_page.locator(".mobile-text-area")

    # Simulate typing multiple characters at once (like a paste or swipe type that emits multiple chars)
    # The term.onData event is triggered by textarea input
    # In playwright, fill() replaces the whole content, effectively sending a multi-char string.
    textarea.evaluate(
        "el => { el.value = 'hello'; el.dispatchEvent(new Event('input', { bubbles: true })); }"
    )

    # Wait for processing
    mobile_page.wait_for_timeout(200)

    # Verify Ctrl is no longer active
    expect(mobile_page.locator("#ctrl-toggle")).not_to_have_class(
        re.compile(r".*active.*")
    )
