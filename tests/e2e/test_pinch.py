import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        device = p.devices["Pixel 5"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=15000)
        yield page
        context.close()
        browser.close()


def test_pinch(mobile_page):
    mobile_page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    mobile_page.click("text=Start New")
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)

    # Allow time for initial setup
    mobile_page.wait_for_timeout(1000)
    initial_height = mobile_page.evaluate("document.body.style.height")
    print(f"Initial height: {initial_height}")

    client = mobile_page.context.new_cdp_session(mobile_page)
    # Use synthesizePinchGesture
    client.send(
        "Input.synthesizePinchGesture",
        {
            "x": 200,
            "y": 200,
            "scaleFactor": 2.0,
            "relativeSpeed": 800,
            "gestureSourceType": "touch",
        },
    )

    mobile_page.wait_for_timeout(1000)
    new_height = mobile_page.evaluate("document.body.style.height")
    print(f"New height: {new_height}")

    scale = mobile_page.evaluate(
        "window.visualViewport ? window.visualViewport.scale : 1.0"
    )
    print(f"Scale: {scale}")
    # Application intentionally disables zoom with user-scalable=no
    assert scale == 1.0
