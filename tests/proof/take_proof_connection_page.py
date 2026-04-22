import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.timeout(60)
def test_take_connection_page_proofs(server, playwright):
    browser = playwright.chromium.launch(headless=True)

    # Desktop
    context_desktop = browser.new_context(viewport={"width": 1280, "height": 720})
    page_desktop = context_desktop.new_page()
    page_desktop.goto(server)
    page_desktop.wait_for_selector(".launcher", state="visible", timeout=10000)
    page_desktop.wait_for_timeout(2000)
    page_desktop.screenshot(
        path="docs/qa-images/connection_page_desktop.png", full_page=True
    )
    context_desktop.close()

    # Mobile
    device = playwright.devices["Pixel 5"]
    context_mobile = browser.new_context(**device)
    page_mobile = context_mobile.new_page()
    page_mobile.goto(server)
    page_mobile.wait_for_selector(".launcher", state="visible", timeout=10000)
    page_mobile.wait_for_timeout(2000)
    page_mobile.screenshot(
        path="docs/qa-images/connection_page_mobile.png", full_page=True
    )
    context_mobile.close()

    browser.close()
