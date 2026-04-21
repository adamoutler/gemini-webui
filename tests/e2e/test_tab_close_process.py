import pytest
import time
from playwright.sync_api import Page, expect
import subprocess
import os


def test_tab_close_terminates_process(page: Page, server):
    # Log in and start a tab
    page.goto(server)

    # Wait for the launcher or start a new connection
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)
    page.click('text="Start New"')

    # Wait for terminal to be ready
    page.wait_for_selector(".xterm-helper-textarea", state="attached", timeout=15000)

    # Type a long-running command
    page.keyboard.type("sleep 300\n")
    time.sleep(1)  # Give it a second to spawn

    # We don't easily know the PID from the frontend, but we can check if a sleep process exists.
    # Alternatively, we just close the tab and check there are no zombies or sleep processes.
    try:
        sleep_procs_before = (
            subprocess.check_output(["pgrep", "-f", "sleep 300"])
            .decode("utf-8")
            .strip()
            .split("\n")
        )
    except subprocess.CalledProcessError:
        sleep_procs_before = []

    # Assuming at least one sleep process was spawned by us

    # Close the tab by clicking the 'x' button
    # The active tab has an x button.
    close_button = page.locator(".tab.active .tab-close")
    expect(close_button).to_be_visible()

    # Listen to dialog if any and accept it
    page.on("dialog", lambda dialog: dialog.accept())

    close_button.click()

    # Wait a bit for backend termination
    time.sleep(1.5)

    # Now check sleep processes again
    try:
        sleep_procs_after = (
            subprocess.check_output(["pgrep", "-f", "sleep 300"])
            .decode("utf-8")
            .strip()
            .split("\n")
        )
    except subprocess.CalledProcessError:
        sleep_procs_after = []

    assert len(sleep_procs_after) < max(
        1, len(sleep_procs_before)
    ), "Sleep process should be terminated"
