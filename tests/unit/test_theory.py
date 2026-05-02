import pytest
from playwright.sync_api import expect


@pytest.mark.timeout(60)
def test_theory(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # Intercept REST API to simulate failure
    page.route(
        "**/api/sessions*",
        lambda route: route.fulfill(
            status=500, json={"error": "Internal Server Error"}
        ),
    )

    page.goto(server, timeout=15000)
    page.wait_for_selector(".launcher", state="attached", timeout=15000)

    local_health = page.locator(
        'div[data-label="local"] .connection-title span[id$="_health_local"]'
    )

    # Red because the REST API returns 500 during the polling loop
    expect(local_health).to_have_text("🔴", timeout=10000)

    browser.close()
