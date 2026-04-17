import pytest
import re
from playwright.sync_api import Page, expect


@pytest.fixture(scope="function")
def page(server, playwright):
    from playwright.sync_api import sync_playwright

    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(60000)
    page.goto(server)
    yield page
    context.close()
    browser.close()


def test_mobile_layout_locked(page, server, playwright):
    # Emulate iPhone 12
    from playwright.sync_api import sync_playwright

    # We need a new context with mobile emulation
    browser = page.context.browser
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        is_mobile=True,
        has_touch=True,
    )
    mobile_page = context.new_page()
    mobile_page.goto(f"{server}/")

    # Check if is-mobile class is on html (documentElement)
    # Wait for app to initialize
    expect(mobile_page.locator("html")).to_have_class(
        re.compile(r".*is-mobile.*"), timeout=10000
    )

    # Check if body has overflow: hidden and position: fixed
    # Note: the CSS uses .is-mobile body { ... }
    overflow = mobile_page.evaluate("window.getComputedStyle(document.body).overflow")
    position = mobile_page.evaluate("window.getComputedStyle(document.body).position")

    assert overflow == "hidden"
    assert position == "fixed"

    # Check if touch-action is none on body
    touch_action = mobile_page.evaluate(
        "window.getComputedStyle(document.body).touchAction"
    )
    assert touch_action == "none"

    # Check if toolbar has touch-action: pan-y (for pull-to-refresh)
    toolbar_touch = mobile_page.evaluate(
        "window.getComputedStyle(document.getElementById('toolbar')).touchAction"
    )
    assert "pan-y" in toolbar_touch

    mobile_page.screenshot(path="public/qa-screenshots/proof_270_mobile_locked.png")
    context.close()


def test_visual_viewport_listener_exists(page, server, playwright):
    page.goto(f"{server}/")
    # Check if appVisualViewport is defined (it should be window.visualViewport or a mock)
    is_defined = page.evaluate("typeof window.appVisualViewport !== 'undefined'")
    assert is_defined
