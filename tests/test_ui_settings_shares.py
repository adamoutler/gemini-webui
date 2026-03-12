import pytest
import time
import re
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(60000)
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(60)
def test_ui_settings_shared_sessions(page, server):
    """Verify that a user can view and delete shared sessions from Settings."""
    # 1. Start a fresh local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    # Wait for terminal to appear
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=15000)
    expect(page.locator('.xterm-screen')).to_be_visible(timeout=15000)
    
    time.sleep(1) # Wait for terminal render
    
    # 2. Click Share Session to create a share
    page.locator('#share-session-btn').click()
    expect(page.locator('#share-modal')).to_be_visible(timeout=15000)
    
    # Generate Share Link
    with page.expect_request("**/api/shares/create") as req_info:
        page.locator('#confirm-share-btn').click()
    expect(page.locator('#share-result')).to_be_visible(timeout=15000)
    
    # Close share modal
    page.locator('#share-modal .modal-content span').click()
    
    # 3. Open Settings
    page.locator('button:has-text("Settings")').click()
    expect(page.locator('#settings-modal')).to_be_visible(timeout=15000)
    
    # 4. Verify Session Snapshots section exists and has the item
    shared_list = page.locator('#shared-sessions-list')
    expect(shared_list).to_be_visible(timeout=15000)

    # It should have at least one session item
    items_count_before = shared_list.locator('.session-item').count()
    assert items_count_before > 0

    session_item = shared_list.locator('.session-item').first
    expect(session_item).to_be_visible(timeout=15000)
    expect(session_item).to_contain_text("Delete")
    expect(session_item).to_contain_text("Copy")
    expect(session_item).to_contain_text("View")

    # Click View and ensure the preview modal opens
    session_item.locator('button.primary', has_text="View").click()
    preview_modal = page.locator('#preview-modal')
    expect(preview_modal).to_be_visible(timeout=15000)

    # Check that iframe has src
    iframe = page.locator('#preview-iframe')
    expect(iframe).to_have_attribute('src', re.compile(r'/s/.+'))

    # Wait for the iframe content to load to ensure it's not a broken link
    # (Optional, but good for stability)
    time.sleep(1)

    # Close preview modal
    preview_modal.locator('span').click()
    expect(preview_modal).to_be_hidden(timeout=15000)

    # Accept the confirm dialog when deleting
    page.on("dialog", lambda dialog: dialog.accept())

    # 5. Delete the shared session
    with page.expect_request_finished(lambda request: request.method == "DELETE" and "/api/shares/" in request.url):
        session_item.locator('button.danger').click()

    # Give it a moment to refresh the list
    time.sleep(1)

    # Verify the item count decreased
    items_count_after = shared_list.locator('.session-item').count()
    assert items_count_after == items_count_before - 1
