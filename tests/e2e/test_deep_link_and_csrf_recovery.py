import pytest
import time
from playwright.sync_api import Page, expect


@pytest.fixture(autouse=True)
def setup_server():
    # Server should be already running on 5001 with BYPASS_AUTH_FOR_TESTING=true
    pass


def test_deep_link_adhoc(page: Page):
    target = "test@localhost:2222"
    url = f"http://127.0.0.1:5001/?target={target}"
    page.goto(url)

    # Check if a tab is created and starts connecting
    # The tab title should be the target's host part (localhost:2222)
    expect(page.locator(".tab.active span").first).to_contain_text("localhost:2222")

    # Check if it attempts to connect (look for terminal output or "Establishing connection")
    # Since it's a fake target, it might show an error eventually, but we check for initial state
    expect(page.locator(".terminal")).to_be_visible()
    page.screenshot(path="public/qa-screenshots/proof_311_adhoc.png")


def test_deep_link_host(page: Page):
    host_label = "local"
    url = f"http://127.0.0.1:5001/?host={host_label}"
    page.goto(url)

    # Check if a tab is created with title "local"
    expect(page.locator(".tab.active span").first).to_contain_text("local")
    expect(page.locator(".terminal")).to_be_visible()
    page.screenshot(path="public/qa-screenshots/proof_311_host.png")


def test_csrf_recovery_loop(page: Page):
    # This test might be tricky to trigger naturally.
    # We can try to simulate it by intercepting /api/csrf-token and returning 403 or 400
    # until the loop breaks.

    url = "http://127.0.0.1:5001/"
    page.goto(url)

    # Mock /api/csrf-token to always fail
    page.route(
        "**/api/csrf-token", lambda route: route.fulfill(status=403, body="Forbidden")
    )

    # Manually trigger a CSRF refresh by calling the function in the browser
    # or by performing an action that triggers it.
    # In app.js, refreshCsrfToken is called on 400/403 errors from fetch.

    page.evaluate("""() => {
        for(let i=0; i<15; i++) {
            refreshCsrfToken().catch(e => console.log('Expected error:', e.message));
        }
    }""")

    # Check if the modal appears
    expect(page.locator("#connection-issue-modal")).to_be_visible()
    expect(page.locator("#connection-issue-details")).to_contain_text(
        "Too many CSRF refresh attempts"
    )

    # Check if reload button exists
    expect(page.locator("#connection-issue-modal button")).to_contain_text(
        "Reload Page"
    )
    page.screenshot(path="public/qa-screenshots/proof_310_csrf_modal.png")
