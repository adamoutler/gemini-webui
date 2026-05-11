import pytest
from playwright.sync_api import expect


@pytest.mark.timeout(30)
def test_automation_ui(server, playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()

    page.goto(f"{server}/")

    # Wait for the UI to settle
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )

    # Click the Schedule button to open Automation Dashboard
    page.click("text=Schedule", force=True)

    # Wait for modal to be visible
    page.wait_for_selector("#automation-modal", state="visible")

    # Take screenshot of the Automation modal
    page.screenshot(path="public/qa-screenshots/automation_dashboard_modal.png")
    page.screenshot(path="docs/qa-images/automation_dashboard_modal.png")

    # Fill out the form
    page.fill("#automation-name", "Test UI Schedule")
    page.fill(
        "#automation-prompt",
        "This is an auto-resizing text area testing input\\nLine 2\\nLine 3",
    )
    page.fill("#automation-recurrence-freq", "2")
    page.select_option("#automation-recurrence-unit", "months")

    # Take screenshot of the filled form
    page.screenshot(path="public/qa-screenshots/automation_dashboard_filled.png")

    # Save the schedule
    page.click("button:has-text('Save Schedule')")

    # Wait for alert mock or fetch to finish
    page.wait_for_timeout(1000)

    # It should appear in the active schedules
    expect(page.locator("#automation-schedules-list")).to_contain_text(
        "Test UI Schedule"
    )

    # Switch to history tab
    page.click("#tab-history")
    page.wait_for_selector("#automation-history-view", state="visible")

    # Take screenshot of history tab
    page.screenshot(path="public/qa-screenshots/automation_history_tab.png")

    context.close()
    browser.close()
