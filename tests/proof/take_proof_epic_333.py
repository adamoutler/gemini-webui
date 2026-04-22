import pytest
from playwright.sync_api import expect


@pytest.mark.timeout(60)
def test_take_proof_epic_333(server, playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto(server)
    page.wait_for_selector(".launcher", state="attached", timeout=15000)
    page.screenshot(path="docs/qa-images/epic_333_connection_page.png", full_page=True)
    browser.close()
