import pytest
import re
from playwright.sync_api import expect
import time


@pytest.mark.timeout(30)
def test_task_monitor(page, server, test_data_dir):
    """Verify that the Task Monitor displays active sessions and allows killing them."""
    page.goto(server)

    # Start a new session
    page.wait_for_selector(".launcher", state="attached", timeout=15000)
    page.click("text=Start New", timeout=10000)
    page.wait_for_selector(".terminal-instance", timeout=10000)

    # Open settings
    page.locator('button[data-onclick="openSettings()"]').click()
    page.wait_for_selector("#settings-modal", state="visible")

    # Open Task Monitor
    page.click("text=Task Monitor")
    page.wait_for_selector("#task-monitor-modal", state="visible")

    # Wait for the tasks list to load
    page.wait_for_selector("text=Local", timeout=5000)
    page.wait_for_selector("text=Active", timeout=5000)

    # Check that a Kill button is present
    kill_btn = page.locator("#task-monitor-list button:has-text('Kill')").first
    expect(kill_btn).to_be_visible()

    page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
    # Setup dialog handler to accept the confirm dialog
    page.once("dialog", lambda dialog: dialog.accept())

    # Click Kill
    kill_btn.click()

    # Wait for refresh and the connection to disappear or show "No active tasks"
    try:
        page.wait_for_selector("text=No active connections found.", timeout=5000)
    except Exception:
        page.screenshot(path="public/qa-screenshots/task_monitor_kill_fail.png")
        raise
