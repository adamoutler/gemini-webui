import pytest
from playwright.sync_api import expect, sync_playwright
import time
from tests.utils.playwright_mobile_utils import (
    simulateAutocorrect,
    simulateSpacebarTrackpad,
)


@pytest.fixture(scope="function")
def ios_page(server):
    with sync_playwright() as p:
        iphone = p.devices["iPhone 12"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


@pytest.fixture(scope="function")
def android_page(server):
    with sync_playwright() as p:
        pixel = p.devices["Pixel 5"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**pixel)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


def get_terminal_text(page):
    return page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : ''; }"
    )


@pytest.mark.timeout(60)
def test_mobile_utils_webkit(ios_page):
    # Start a fresh session
    btns = ios_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(ios_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = ios_page.locator(".mobile-text-area")
    textarea.focus()

    # Just ensure the utility functions execute without exceptions
    simulateAutocorrect(ios_page, "teh", "the")
    simulateSpacebarTrackpad(ios_page, -1)

    assert True


@pytest.mark.timeout(60)
def test_mobile_utils_chromium(android_page):
    # Start a fresh session
    btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(android_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    textarea = android_page.locator(".mobile-text-area")
    textarea.focus()

    # Just ensure the utility functions execute without exceptions
    simulateAutocorrect(android_page, "teh", "the")
    simulateSpacebarTrackpad(android_page, -1)

    assert True
