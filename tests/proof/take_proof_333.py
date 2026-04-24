import pytest
from playwright.sync_api import expect
import os


@pytest.mark.timeout(120)
def test_take_proof_333(page, server):
    # Navigate to the connection page
    page.goto(server)
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)

    # Hover over the quick connect button
    page.hover(".quick-connect-bar button.primary")

    # Take a screenshot of the quick connect bar
    os.makedirs("docs/qa-images", exist_ok=True)
    page.screenshot(path="docs/qa-images/epic_333_quick_connect.png")

    # Expand the local session
    session_item = page.locator(".session-item").first
    if session_item.is_visible():
        session_item.hover()
        page.screenshot(path="docs/qa-images/epic_333_session_hover.png")

    # Take a screenshot of the full launcher
    page.locator(".launcher").first.screenshot(
        path="docs/qa-images/epic_333_launcher.png"
    )

    print("Screenshots taken successfully!")
