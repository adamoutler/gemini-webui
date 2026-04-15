import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.fixture(scope="function")
def mobile_page(server, playwright):
    p = playwright
    if True:
        device = p.devices["Pixel 5"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


@pytest.mark.timeout(20)
def test_super_undo_button(mobile_page):
    """
    Test that the Super button is rendered in the mobile controls,
    and the A+ and A- buttons are grouped.
    """
    page = mobile_page

    # Start a session to be in terminal mode
    page.click("text=Start New")
    page.wait_for_selector(".terminal-instance", timeout=10000)
    page.wait_for_selector("#mobile-controls", state="visible", timeout=5000)

    mobile_controls = page.locator("#mobile-controls")

    # Check for the Super button
    super_button = mobile_controls.locator("div.control-btn").get_by_text(
        "Super", exact=True
    )
    expect(super_button).to_be_visible()

    # Check for the grouped A- and A+ buttons
    btn_group = mobile_controls.locator(".control-btn-group")
    expect(btn_group).to_be_visible()

    a_minus = btn_group.locator(".left").get_by_text("A-", exact=True)
    expect(a_minus).to_have_attribute("data-func-adjust", "-1")
    expect(a_minus).to_be_visible()

    a_plus = btn_group.locator(".right").get_by_text("A+", exact=True)
    expect(a_plus).to_have_attribute("data-func-adjust", "1")
    expect(a_plus).to_be_visible()
