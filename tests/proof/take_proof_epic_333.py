import pytest
from playwright.sync_api import expect
import time


@pytest.mark.timeout(60)
def test_take_proof_epic_333(server, playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto(server)

    try:
        page.wait_for_selector(".launcher", state="visible", timeout=5000)
    except Exception:
        # If it's not visible, maybe a session auto-started. Let's click + New
        page.locator("#new-tab-btn").click()
        page.wait_for_selector(".launcher", state="visible", timeout=10000)

    # Wait for the DOM to settle and connection cards to be ready
    page.wait_for_selector(".connection-card", state="visible", timeout=10000)

    # Wait for any network requests/animations
    page.wait_for_timeout(2000)

    page.screenshot(path="docs/qa-images/epic_333_connection_page.png", full_page=True)
    browser.close()
